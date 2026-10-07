"""Persistence queries always retain the source order and saved customer scope."""
from sqlalchemy.orm import aliased
from sqlmodel import func, select

from models import Customer, CustomerBranch, CustomerEquipment, Order
from models.maintenance_observation import MaintenanceObservation, MaintenanceObservationPhoto, MaintenanceObservationRevision
from services.tenant_scope_service import storefront_scope_clause, tenant_scope_clause


class MaintenanceObservationDAO:
    @staticmethod
    def scoped(scope):
        current_customer = aliased(Customer)
        return (select(MaintenanceObservation)
                .join(Order, Order.id == MaintenanceObservation.source_order_id)
                .join(Customer, Customer.id == MaintenanceObservation.customer_id)
                .outerjoin(current_customer, current_customer.id == Order.customer_id)
                .outerjoin(CustomerBranch, CustomerBranch.id == MaintenanceObservation.customer_branch_id)
                .outerjoin(CustomerEquipment, CustomerEquipment.id == MaintenanceObservation.equipment_id)
                .where(storefront_scope_clause(MaintenanceObservation, scope),
                       storefront_scope_clause(Order, scope), tenant_scope_clause(Customer, scope),
                       (Order.customer_id.is_(None)) | tenant_scope_clause(current_customer, scope),
                       MaintenanceObservation.customer_branch_id.is_(None) | (CustomerBranch.customer_id == MaintenanceObservation.customer_id),
                       MaintenanceObservation.equipment_id.is_(None) | (
                           (CustomerEquipment.customer_id == MaintenanceObservation.customer_id))))

    @classmethod
    async def get(cls, session, observation_id, scope, *, lock=False):
        statement = cls.scoped(scope).where(MaintenanceObservation.id == observation_id)
        if lock:
            statement = statement.with_for_update(of=MaintenanceObservation).execution_options(populate_existing=True)
        return (await session.execute(statement)).scalars().first()

    @classmethod
    async def list(cls, session, scope, *, order_id=None, equipment_id=None, limit=50, offset=0):
        statement = cls.scoped(scope)
        if order_id is not None:
            statement = statement.where(MaintenanceObservation.source_order_id == order_id)
        if equipment_id is not None:
            statement = statement.where(MaintenanceObservation.equipment_id == equipment_id)
        total = await session.scalar(select(func.count()).select_from(statement.subquery()))
        items = (await session.execute(statement.order_by(MaintenanceObservation.id.desc()).limit(limit).offset(offset))).scalars().all()
        return {"items": items, "total": total}

    @staticmethod
    async def by_command(session, order_id, key):
        return await session.scalar(select(MaintenanceObservation).where(
            MaintenanceObservation.source_order_id == order_id, MaintenanceObservation.command_key == key))

    @staticmethod
    async def revisions(session, observation_id):
        return (await session.execute(select(MaintenanceObservationRevision).where(
            MaintenanceObservationRevision.observation_id == observation_id
        ).order_by(MaintenanceObservationRevision.version))).scalars().all()

    @staticmethod
    async def photos(session, observation_id):
        return (await session.execute(select(MaintenanceObservationPhoto).where(
            MaintenanceObservationPhoto.observation_id == observation_id
        ).order_by(MaintenanceObservationPhoto.id))).scalars().all()
