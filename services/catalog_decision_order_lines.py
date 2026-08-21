from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import OrderProductLink
from services.catalog_decision_projection import CatalogDecisionProductSnapshot
from services.order_product_line_service import OrderProductLineService


class CatalogDecisionOrderLineService:
    """Replace one proposal with authoritative catalog-decision snapshots."""

    @staticmethod
    async def replace(
        session: AsyncSession,
        *,
        order_id: int,
        proposal_id: int,
        product_ids: list[int],
        snapshots: dict[int, CatalogDecisionProductSnapshot],
    ) -> None:
        await OrderProductLineService.reconcile(
            session,
            order_id=order_id,
            proposal_id=proposal_id,
            lines=[
                {
                    "product_id": product_id,
                    "quantity": 1,
                    "price": snapshots[product_id].retail_price_byn,
                    "cost": snapshots[product_id].purchase_cost_byn,
                    "logistics_components": None,
                }
                for product_id in product_ids
            ],
        )
        await session.flush()
        links = list(
            (
                await session.execute(
                    select(OrderProductLink).where(
                        OrderProductLink.order_id == order_id,
                        OrderProductLink.proposal_id == proposal_id,
                    )
                )
            ).scalars().all()
        )
        for link in links:
            snapshot = snapshots[int(link.product_id)]
            link.title_snapshot = snapshot.product.title
            link.currency_snapshot = "BYN"
            session.add(link)
