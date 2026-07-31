"""Transactional Manager order deletion with durable external cleanup."""

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from models.order import (
    BankReceipt,
    Order,
    OrderDocument,
    OrderInstaller,
    OrderProductLink,
    OrderProposal,
    OrderServiceLink,
    OrderWorkStage,
    OutgoingEmail,
    Payment,
)
from services.command_transaction import command_transaction
from services.document_service import DocumentService
from services.order_document_cleanup_service import OrderDocumentCleanupService
from services.tenant_entity_access_service import TenantEntityAccessService
from services.tenant_scope_service import TenantScope


class OrderDeleteCommandService:
    @staticmethod
    async def delete_order(
        session: AsyncSession,
        order_id: int,
        *,
        tenant_scope: TenantScope,
    ) -> bool:
        async with command_transaction(session):
            order = await TenantEntityAccessService.get_order(
                session,
                order_id,
                tenant_scope=tenant_scope,
                for_update=True,
            )
            if not order:
                raise ValueError(f"Order {order_id} not found")

            documents = await DocumentService.list_order_documents(
                session,
                order_id,
                tenant_scope=tenant_scope,
            )
            await OrderDocumentCleanupService.enqueue_order_documents(
                session,
                order_id=order_id,
                documents=documents or [],
                tenant_scope=tenant_scope,
            )

            # Keep audit/history rows but detach them from the hard-deleted order.
            await session.execute(
                sa.update(BankReceipt)
                .where(BankReceipt.matched_order_id == order_id)
                .values(
                    status="requires_review",
                    matched_order_id=None,
                    matched_payment_id=None,
                    match_meta={
                        "reason": "matched_order_deleted",
                        "deleted_order_id": order_id,
                    },
                )
            )
            await session.execute(
                sa.update(OutgoingEmail)
                .where(OutgoingEmail.order_id == order_id)
                .values(order_id=None)
            )
            await session.execute(
                sa.delete(OrderProductLink).where(
                    OrderProductLink.order_id == order_id
                )
            )
            await session.execute(
                sa.delete(OrderServiceLink).where(
                    OrderServiceLink.order_id == order_id
                )
            )
            await session.execute(
                sa.delete(OrderWorkStage).where(OrderWorkStage.order_id == order_id)
            )
            await session.execute(
                sa.delete(OrderInstaller).where(OrderInstaller.order_id == order_id)
            )
            await session.execute(
                sa.delete(Payment).where(Payment.order_id == order_id)
            )
            await session.execute(
                sa.delete(OrderDocument).where(OrderDocument.order_id == order_id)
            )
            await session.execute(
                sa.delete(OrderProposal).where(OrderProposal.order_id == order_id)
            )
            await session.execute(sa.delete(Order).where(Order.id == order_id))
            await session.flush()

        return True
