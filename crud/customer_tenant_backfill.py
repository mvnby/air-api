from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Sequence

from sqlalchemy import exists, func, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Customer, CustomerRequisitesRecognition, Tenant


@dataclass(frozen=True)
class TenantOwnedEntityCounts:
    entity: str
    total: int
    legacy_null: int
    target_scoped: int
    unexpected_scoped: int
    unknown_tenant: int

    def to_dict(self) -> dict[str, int | str]:
        return asdict(self)


class CustomerTenantBackfillDAO:
    """Persistence primitives for bounded Customer ownership backfill."""

    LOCK_KEY = "mvn:customer-tenant-scope-backfill:v1"

    @staticmethod
    def entity_name(entity: Any) -> str:
        if entity is Customer:
            return "customer"
        if entity is CustomerRequisitesRecognition:
            return "recognition"
        raise ValueError("Unsupported Customer tenant backfill entity")

    @staticmethod
    async def try_acquire_transaction_lock(session: AsyncSession) -> bool:
        if session.get_bind().dialect.name != "postgresql":
            return True
        acquired = await session.scalar(
            text("SELECT pg_try_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": CustomerTenantBackfillDAO.LOCK_KEY},
        )
        return bool(acquired)

    @staticmethod
    async def inspect(
        session: AsyncSession,
        *,
        entity: Any,
        tenant_id: int,
    ) -> TenantOwnedEntityCounts:
        tenant_exists = exists(
            select(Tenant.id).where(Tenant.id == entity.tenant_id)
        ).correlate(entity)
        row = (
            await session.execute(
                select(
                    func.count(entity.id),
                    func.count(entity.id).filter(entity.tenant_id.is_(None)),
                    func.count(entity.id).filter(entity.tenant_id == tenant_id),
                    func.count(entity.id).filter(
                        entity.tenant_id.is_not(None),
                        entity.tenant_id != tenant_id,
                    ),
                    func.count(entity.id).filter(
                        entity.tenant_id.is_not(None),
                        ~tenant_exists,
                    ),
                ).select_from(entity)
            )
        ).one()
        values = [int(value or 0) for value in row]
        return TenantOwnedEntityCounts(
            entity=CustomerTenantBackfillDAO.entity_name(entity),
            total=values[0],
            legacy_null=values[1],
            target_scoped=values[2],
            unexpected_scoped=values[3],
            unknown_tenant=values[4],
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
            .where(entity.tenant_id.is_(None))
            .order_by(entity.id.asc())
            .limit(limit)
        )
        if lock_rows and session.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update(nowait=True)
        rows = (await session.execute(statement)).scalars().all()
        return [int(row_id) for row_id in rows]

    @staticmethod
    async def assign_tenant(
        session: AsyncSession,
        *,
        entity: Any,
        ids: Sequence[int],
        tenant_id: int,
    ) -> list[int]:
        expected_ids = sorted({int(row_id) for row_id in ids})
        if not expected_ids:
            return []

        values: dict[str, Any] = {"tenant_id": tenant_id}
        if entity is CustomerRequisitesRecognition:
            # Preserve business recency: SQLAlchemy otherwise applies Python
            # ``onupdate`` during this technical ownership backfill.
            values["updated_at"] = entity.updated_at
        result = await session.execute(
            update(entity)
            .where(
                entity.id.in_(expected_ids),
                entity.tenant_id.is_(None),
            )
            .values(**values)
            .returning(entity.id)
        )
        return sorted(int(row_id) for row_id in result.scalars().all())
