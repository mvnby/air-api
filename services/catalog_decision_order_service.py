from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from models import OrderProposal
from models.tenancy import TenantScope
from services.catalog_decision_projection import CatalogDecisionQueryService
from services.catalog_decision_order_lines import CatalogDecisionOrderLineService
from services.command_transaction import command_transaction
from services.order_proposal_command_service import OrderProposalCommandService
from services.order_service import OrderService


class CatalogDecisionOrderConflict(ValueError):
    """The order gained products after the attach dialog was opened."""


class CatalogDecisionOrderService:
    """Atomic bridge from the system catalog basket to one order proposal."""

    @staticmethod
    async def attach(
        session: AsyncSession,
        *,
        order_id: int,
        product_ids: list[int],
        mode: str,
        tenant_scope: TenantScope,
    ) -> dict[str, Any]:
        ids = [int(product_id) for product_id in product_ids]
        if len(ids) != len(set(ids)):
            raise ValueError("Один товар нельзя добавить дважды")

        async with command_transaction(session):
            order = await OrderProposalCommandService._load_order_for_write(
                session,
                order_id,
                tenant_scope=tenant_scope,
            )
            if OrderService._status_value(order.status) != "negotiation":
                raise ValueError("К корзине можно привязать только заказ в переговорах")

            snapshots = await CatalogDecisionQueryService.get_system_product_snapshots(
                session,
                tenant_scope=tenant_scope,
                product_ids=ids,
            )
            if len(snapshots) != len(ids):
                missing = [product_id for product_id in ids if product_id not in snapshots]
                raise ValueError(f"Товары не найдены: {', '.join(map(str, missing))}")

            active_proposals = [proposal for proposal in order.proposals if not proposal.is_archived]
            active_ids = {int(proposal.id) for proposal in active_proposals if proposal.id is not None}
            has_products = any(link.proposal_id in active_ids for link in order.product_links)
            if has_products and mode == "auto":
                raise CatalogDecisionOrderConflict(
                    "В заказе уже есть товары. Выберите замену основного предложения или новый вариант."
                )

            if not has_products or mode == "replace_selected":
                proposal = OrderService._selected_proposal(order)
                if proposal is None:
                    raise RuntimeError("У заказа не создано основное предложение")
            elif mode == "new_alternative":
                proposal = OrderProposal(
                    order_id=order_id,
                    name=f"Вариант {len(active_proposals) + 1}",
                    status="draft",
                    is_selected=False,
                    sort_order=len(active_proposals) * 10,
                )
                session.add(proposal)
                await session.flush()
            else:
                raise ValueError("Неизвестный режим добавления товаров")

            await CatalogDecisionOrderLineService.replace(
                session,
                order_id=order_id,
                proposal_id=int(proposal.id),
                product_ids=ids,
                snapshots=snapshots,
            )
            await OrderService._refresh_order_financials(session, order)
            session.add(order)

        return await OrderProposalCommandService._project_committed_order(
            session,
            order_id,
            tenant_scope=tenant_scope,
        )
