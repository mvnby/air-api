"""Persistence queries for explicit installer publications, never CRM serialization."""

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models import (
    CustomerEquipment,
    EquipmentOrderLink,
    Order,
    OrderAttachmentLink,
    ServiceAttachment,
)
from models.installer_publication import (
    InstallerCollectionInstruction,
    InstallerMaterialPublication,
)
from services.tenant_entity_access_service import TenantEntityAccessService
from services.tenant_scope_service import tenant_scope_clause


class InstallerWorkspaceDAO:
    @staticmethod
    async def orders(session, scope, order_ids):
        from models import Customer

        rows = await session.scalars(
            select(Order)
            .outerjoin(Customer)
            .where(
                Order.id.in_(order_ids),
                TenantEntityAccessService.order_clause(scope),
                TenantEntityAccessService.order_customer_clause(scope),
            )
            .options(
                selectinload(Order.customer),
                selectinload(Order.proposals),
                selectinload(Order.product_links),
                selectinload(Order.service_links),
                selectinload(Order.payments),
            )
            .execution_options(populate_existing=True)
        )
        return {order.id: order for order in rows.all()}

    @staticmethod
    async def order(session, scope, order_id, *, lock=False):
        return await TenantEntityAccessService.get_order(
            session,
            order_id,
            tenant_scope=scope,
            for_update=lock,
            populate_existing=True,
            options=(
                selectinload(Order.customer),
                selectinload(Order.proposals),
                selectinload(Order.product_links),
                selectinload(Order.service_links),
                selectinload(Order.payments),
            ),
        )

    @staticmethod
    async def collection(session, order_id):
        return await session.scalar(
            select(InstallerCollectionInstruction)
            .where(
                InstallerCollectionInstruction.order_id == order_id,
            )
            .execution_options(populate_existing=True)
        )

    @staticmethod
    async def publications(session, assignment_id):
        return list(
            (
                await session.scalars(
                    select(InstallerMaterialPublication)
                    .where(
                        InstallerMaterialPublication.assignment_id == assignment_id,
                    )
                    .execution_options(populate_existing=True)
                )
            ).all()
        )

    @staticmethod
    async def materials(session, order_id):
        return list(
            (
                await session.execute(
                    select(OrderAttachmentLink, ServiceAttachment)
                    .join(
                        ServiceAttachment,
                        ServiceAttachment.id == OrderAttachmentLink.attachment_id,
                    )
                    .where(
                        OrderAttachmentLink.order_id == order_id,
                        OrderAttachmentLink.archived_at.is_(None),
                        ServiceAttachment.archived_at.is_(None),
                    )
                    .execution_options(populate_existing=True)
                )
            ).all()
        )

    @staticmethod
    async def equipment(session, order, scope):
        from models import Customer

        linked = select(EquipmentOrderLink.equipment_id).where(
            EquipmentOrderLink.order_id == order.id
        )
        return list(
            (
                await session.scalars(
                    select(CustomerEquipment)
                    .join(
                        Customer,
                        Customer.id == CustomerEquipment.customer_id,
                    )
                    .where(
                        tenant_scope_clause(Customer, scope),
                        CustomerEquipment.customer_id == order.customer_id,
                        CustomerEquipment.is_archived.is_(False),
                        (CustomerEquipment.id.in_(linked))
                        | (CustomerEquipment.source_order_id == order.id),
                    )
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
