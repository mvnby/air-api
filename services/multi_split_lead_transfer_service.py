"""Carry a public multi-split request into the draft created from its lead."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    LeadMultiSplitConfiguration,
    Order,
    OrderMultiSplitConfiguration,
    OrderProductLink,
    OrderProposal,
    Product,
)
from services.order_service import OrderService
from services.product_supply_metrics_service import ProductSupplyMetricsService


class MultiSplitLeadTransferService:
    @staticmethod
    async def transfer(session: AsyncSession, *, lead_id: int, order: Order) -> None:
        source = (await session.execute(
            select(LeadMultiSplitConfiguration).where(LeadMultiSplitConfiguration.lead_id == lead_id)
        )).scalar_one_or_none()
        if source is None:
            return

        proposal = OrderProposal(
            order_id=int(order.id),
            name="Мультисплит · заявка с сайта",
            status="draft",
            is_selected=True,
        )
        session.add(proposal)
        await session.flush()

        snapshot = source.component_snapshot or []
        ids = {int(item["product_id"]) for item in snapshot}
        products = (await session.execute(select(Product).where(Product.id.in_(ids)))).scalars().all()
        by_id = {int(product.id): product for product in products}
        if set(by_id) != ids:
            raise ValueError("Компонент мультисплита из заявки отсутствует в каталоге. Проверьте состав перед созданием заказа.")
        metrics = await ProductSupplyMetricsService.compute_for_products(session, products)
        for item in snapshot:
            product_id = int(item["product_id"])
            raw_cost = metrics.get(product_id, {}).get("min_cost_byn")
            session.add(OrderProductLink(
                order_id=int(order.id),
                proposal_id=int(proposal.id),
                product_id=product_id,
                quantity=int(item["quantity"]),
                price=int(item["unit_price_byn"]),
                cost=int(round(float(raw_cost))) if raw_cost is not None else 0,
                title_snapshot=str(item["title"]),
                currency_snapshot="BYN",
            ))

        session.add(OrderMultiSplitConfiguration(
            order_id=int(order.id),
            proposal_id=int(proposal.id),
            rooms=source.rooms,
            component_snapshot=snapshot,
            # Lead snapshots are historical. A fresh review is required before quoting.
            verification_status="requires_specialist",
            profile_id=source.profile_id,
            profile_version=source.profile_version,
            source_url=source.source_url,
            source_version=source.source_version,
        ))
        await session.flush()
        await OrderService._refresh_order_financials(session, order)
