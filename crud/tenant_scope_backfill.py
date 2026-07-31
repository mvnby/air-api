from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Sequence

from sqlalchemy import and_, exists, func, or_, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Lead, Order, Storefront, Tenant
from models.tenancy import TenantScope


@dataclass(frozen=True)
class TenantScopeEntityCounts:
    entity: str
    total: int
    legacy_null: int
    target_scoped: int
    partial: int
    unexpected_scoped: int
    unknown_tenant: int
    unknown_storefront: int
    cross_tenant: int

    def to_dict(self) -> dict[str, int | str]:
        return asdict(self)


class TenantScopeBackfillDAO:
    """Persistence primitives for the bounded Lead/Order provenance backfill."""

    LOCK_KEY = "mvn:lead-order-tenant-scope-backfill:v1"

    @staticmethod
    def entity_name(entity: Any) -> str:
        if entity is Lead:
            return "lead"
        if entity is Order:
            return "order"
        raise ValueError("Tenant scope backfill supports only Lead and Order")

    @staticmethod
    def legacy_clause(entity: Any):
        return and_(
            entity.tenant_id.is_(None),
            entity.storefront_id.is_(None),
        )

    @staticmethod
    async def try_acquire_transaction_lock(session: AsyncSession) -> bool:
        if session.get_bind().dialect.name != "postgresql":
            return True
        acquired = await session.scalar(
            text("SELECT pg_try_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": TenantScopeBackfillDAO.LOCK_KEY},
        )
        return bool(acquired)

    @staticmethod
    async def inspect(
        session: AsyncSession,
        *,
        entity: Any,
        tenant_scope: TenantScope,
    ) -> TenantScopeEntityCounts:
        legacy = TenantScopeBackfillDAO.legacy_clause(entity)
        partial = or_(
            and_(
                entity.tenant_id.is_(None),
                entity.storefront_id.is_not(None),
            ),
            and_(
                entity.tenant_id.is_not(None),
                entity.storefront_id.is_(None),
            ),
        )
        target_scoped = and_(
            entity.tenant_id == tenant_scope.tenant_id,
            entity.storefront_id == tenant_scope.storefront_id,
        )
        unexpected_scoped = and_(
            entity.tenant_id.is_not(None),
            entity.storefront_id.is_not(None),
            or_(
                entity.tenant_id != tenant_scope.tenant_id,
                entity.storefront_id != tenant_scope.storefront_id,
            ),
        )

        tenant_exists = exists(
            select(Tenant.id).where(Tenant.id == entity.tenant_id)
        ).correlate(entity)
        storefront_exists = exists(
            select(Storefront.id).where(Storefront.id == entity.storefront_id)
        ).correlate(entity)
        storefront_matches_tenant = exists(
            select(Storefront.id).where(
                Storefront.id == entity.storefront_id,
                Storefront.tenant_id == entity.tenant_id,
            )
        ).correlate(entity)

        row = (
            await session.execute(
                select(
                    func.count(entity.id),
                    func.count(entity.id).filter(legacy),
                    func.count(entity.id).filter(target_scoped),
                    func.count(entity.id).filter(partial),
                    func.count(entity.id).filter(unexpected_scoped),
                    func.count(entity.id).filter(
                        entity.tenant_id.is_not(None),
                        ~tenant_exists,
                    ),
                    func.count(entity.id).filter(
                        entity.storefront_id.is_not(None),
                        ~storefront_exists,
                    ),
                    func.count(entity.id).filter(
                        entity.tenant_id.is_not(None),
                        entity.storefront_id.is_not(None),
                        tenant_exists,
                        storefront_exists,
                        ~storefront_matches_tenant,
                    ),
                ).select_from(entity)
            )
        ).one()
        values = [int(value or 0) for value in row]
        return TenantScopeEntityCounts(
            entity=TenantScopeBackfillDAO.entity_name(entity),
            total=values[0],
            legacy_null=values[1],
            target_scoped=values[2],
            partial=values[3],
            unexpected_scoped=values[4],
            unknown_tenant=values[5],
            unknown_storefront=values[6],
            cross_tenant=values[7],
        )

    @staticmethod
    async def list_legacy_ids(
        session: AsyncSession,
        *,
        entity: Any,
        limit: int,
        lock_rows: bool,
    ) -> list[int]:
        statement = (
            select(entity.id)
            .where(TenantScopeBackfillDAO.legacy_clause(entity))
            .order_by(entity.id.asc())
            .limit(limit)
        )
        if lock_rows and session.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update(nowait=True)
        rows = (await session.execute(statement)).scalars().all()
        return [int(row_id) for row_id in rows]

    @staticmethod
    async def assign_scope(
        session: AsyncSession,
        *,
        entity: Any,
        ids: Sequence[int],
        tenant_scope: TenantScope,
    ) -> list[int]:
        expected_ids = sorted({int(row_id) for row_id in ids})
        if not expected_ids:
            return []

        result = await session.execute(
            update(entity)
            .where(
                entity.id.in_(expected_ids),
                TenantScopeBackfillDAO.legacy_clause(entity),
            )
            .values(
                tenant_id=tenant_scope.tenant_id,
                storefront_id=tenant_scope.storefront_id,
            )
            .returning(entity.id)
        )
        return sorted(int(row_id) for row_id in result.scalars().all())
