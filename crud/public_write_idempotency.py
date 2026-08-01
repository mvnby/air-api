from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import PublicWriteIdempotency
from services.tenant_scope_service import TenantScope


_CONFLICT_COLUMNS = (
    "tenant_id",
    "storefront_id",
    "command_name",
    "key_hash",
)


class PublicWriteIdempotencyDAO:
    @staticmethod
    async def claim(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        command_name: str,
        key_hash: str,
        request_fingerprint: str,
        expires_at: datetime,
    ) -> PublicWriteIdempotency | None:
        values = {
            "tenant_id": tenant_scope.tenant_id,
            "storefront_id": tenant_scope.storefront_id,
            "command_name": command_name,
            "key_hash": key_hash,
            "request_fingerprint": request_fingerprint,
            "created_at": datetime.now(timezone.utc),
            "expires_at": expires_at,
        }
        dialect_name = session.get_bind().dialect.name
        if dialect_name == "postgresql":
            statement = postgresql_insert(PublicWriteIdempotency).values(**values)
        elif dialect_name == "sqlite":
            statement = sqlite_insert(PublicWriteIdempotency).values(**values)
        else:  # pragma: no cover - production and tests use PostgreSQL/SQLite
            raise RuntimeError(
                f"Unsupported idempotency database dialect: {dialect_name}"
            )
        statement = statement.on_conflict_do_nothing(
            index_elements=list(_CONFLICT_COLUMNS)
        ).returning(PublicWriteIdempotency.id)
        claimed_id = (await session.execute(statement)).scalar_one_or_none()
        if claimed_id is None:
            return None
        return await session.get(PublicWriteIdempotency, int(claimed_id))

    @staticmethod
    async def get_by_scope_key(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        command_name: str,
        key_hash: str,
    ) -> PublicWriteIdempotency | None:
        return await session.scalar(
            select(PublicWriteIdempotency)
            .where(
                PublicWriteIdempotency.tenant_id == tenant_scope.tenant_id,
                PublicWriteIdempotency.storefront_id
                == tenant_scope.storefront_id,
                PublicWriteIdempotency.command_name == command_name,
                PublicWriteIdempotency.key_hash == key_hash,
            )
            .limit(1)
        )
