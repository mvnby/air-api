from datetime import datetime
from hashlib import sha256
from typing import Any, Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import LeadSource, Order, OrderProposal, OrderStatus
from models.tenancy import TenantScope
from services.catalog_decision_order_lines import CatalogDecisionOrderLineService
from services.catalog_decision_projection import (
    CatalogDecisionQueryService,
    SystemCatalogDecisionProjection,
)
from services.command_transaction import command_transaction
from services.order_proposal_command_service import OrderProposalCommandService
from services.order_service import OrderService


class CatalogDecisionQuickOrderService:
    """Create an unidentified negotiation order from the short-lived basket."""

    @staticmethod
    def _fingerprint(*, tenant_scope: TenantScope, idempotency_key: str) -> str:
        raw = (
            f"catalog-decision-quick-order:{tenant_scope.tenant_id}:"
            f"{tenant_scope.storefront_id}:{idempotency_key.strip()}"
        )
        return sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    async def _existing_order_id(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        fingerprint: str,
    ) -> int | None:
        return (
            await session.execute(
                select(Order.id).where(
                    Order.tenant_id == tenant_scope.tenant_id,
                    Order.storefront_id == tenant_scope.storefront_id,
                    Order.source_fingerprint == fingerprint,
                )
            )
        ).scalar_one_or_none()

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        *,
        product_ids: list[int],
        idempotency_key: str,
        prospect_type: Literal["individual", "company"],
        tenant_scope: TenantScope,
    ) -> dict[str, Any]:
        SystemCatalogDecisionProjection.require_scope(tenant_scope)
        ids = [int(product_id) for product_id in product_ids]
        if len(ids) != len(set(ids)):
            raise ValueError("Один товар нельзя добавить дважды")
        if not idempotency_key.strip():
            raise ValueError("Не указан ключ создания заказа")
        fingerprint = cls._fingerprint(
            tenant_scope=tenant_scope,
            idempotency_key=idempotency_key,
        )
        existing_id = await cls._existing_order_id(
            session,
            tenant_scope=tenant_scope,
            fingerprint=fingerprint,
        )
        if existing_id is not None:
            return await OrderProposalCommandService._project_committed_order(
                session,
                existing_id,
                tenant_scope=tenant_scope,
            )

        order_id: int | None = None
        try:
            async with command_transaction(session):
                snapshots = await CatalogDecisionQueryService.get_system_product_snapshots(
                    session,
                    tenant_scope=tenant_scope,
                    product_ids=ids,
                )
                if len(snapshots) != len(ids):
                    missing = [product_id for product_id in ids if product_id not in snapshots]
                    raise ValueError(f"Товары не найдены: {', '.join(map(str, missing))}")

                now = datetime.now()
                order = Order(
                    tenant_id=tenant_scope.tenant_id,
                    storefront_id=tenant_scope.storefront_id,
                    customer_id=None,
                    status=OrderStatus.NEGOTIATION,
                    lead_source=LeadSource.MANAGER,
                    title="Быстрый подбор",
                    source_fingerprint=fingerprint,
                    technical_meta={
                        "order_origin": "catalog_decision",
                        "customer_state": "unidentified",
                        "prospect_type": prospect_type,
                        OrderService.MANAGER_LABELS_META_KEY: [
                            "Быстрый подбор",
                            "Юрлицо" if prospect_type == "company" else "Физлицо",
                        ],
                    },
                    created_at=now,
                    status_changed_at=now,
                )
                session.add(order)
                await session.flush()
                order_id = int(order.id)
                proposal = OrderProposal(
                    order_id=order_id,
                    name="Основное",
                    status="draft",
                    is_selected=True,
                    sort_order=0,
                )
                session.add(proposal)
                await session.flush()
                await CatalogDecisionOrderLineService.replace(
                    session,
                    order_id=order_id,
                    proposal_id=int(proposal.id),
                    product_ids=ids,
                    snapshots=snapshots,
                )
                await OrderService._refresh_order_financials(session, order)
                session.add(order)
        except IntegrityError:
            await session.rollback()
            order_id = await cls._existing_order_id(
                session,
                tenant_scope=tenant_scope,
                fingerprint=fingerprint,
            )
            if order_id is None:
                raise

        if order_id is None:
            raise RuntimeError("Быстрый заказ не был создан")
        return await OrderProposalCommandService._project_committed_order(
            session,
            order_id,
            tenant_scope=tenant_scope,
        )
