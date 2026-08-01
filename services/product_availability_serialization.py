"""Cross-process serialization contract for public availability requests."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.input_validation import normalize_phone_digits
from services.tenant_scope_service import TenantScope


@dataclass(frozen=True)
class ProductAvailabilityLockIdentity:
    normalized_phone: str
    lock_id: int


@dataclass(frozen=True)
class ProductAvailabilitySerializationClaim:
    identity: ProductAvailabilityLockIdentity
    database_now: datetime


class ProductAvailabilitySerialization:
    """Acquire a transaction lock shared by equivalent availability requests."""

    LOCK_NAMESPACE = "mvn:public-product-availability:v1"

    @classmethod
    def build_identity(
        cls,
        *,
        tenant_scope: TenantScope,
        product_id: int,
        phone: str,
    ) -> ProductAvailabilityLockIdentity:
        tenant_id = int(tenant_scope.tenant_id)
        storefront_id = int(tenant_scope.storefront_id)
        normalized_product_id = int(product_id)
        normalized_phone = normalize_phone_digits(phone)
        if tenant_id <= 0 or storefront_id <= 0 or normalized_product_id <= 0:
            raise ValueError("Product availability lock scope is invalid")
        if not normalized_phone:
            raise ValueError("Product availability lock phone is invalid")
        canonical_key = (
            f"{cls.LOCK_NAMESPACE}:{tenant_id}:{storefront_id}:"
            f"{normalized_product_id}:{normalized_phone}"
        )
        lock_id = int.from_bytes(
            hashlib.sha256(canonical_key.encode("utf-8")).digest()[:8],
            byteorder="big",
            signed=True,
        )
        return ProductAvailabilityLockIdentity(
            normalized_phone=normalized_phone,
            lock_id=lock_id,
        )

    @classmethod
    async def acquire(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        product_id: int,
        phone: str,
    ) -> ProductAvailabilitySerializationClaim:
        identity = cls.build_identity(
            tenant_scope=tenant_scope,
            product_id=product_id,
            phone=phone,
        )
        dialect_name = session.get_bind().dialect.name
        if dialect_name == "postgresql":
            # The receipt transaction owns this lock through its final commit.
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:lock_id)"),
                {"lock_id": identity.lock_id},
            )
        database_now = await cls._database_now(
            session,
            dialect_name=dialect_name,
        )
        return ProductAvailabilitySerializationClaim(
            identity=identity,
            database_now=database_now,
        )

    @staticmethod
    async def _database_now(
        session: AsyncSession,
        *,
        dialect_name: str,
    ) -> datetime:
        if dialect_name == "postgresql":
            clock = func.clock_timestamp()
        elif dialect_name == "sqlite":
            clock = func.strftime("%Y-%m-%d %H:%M:%f", "now")
        else:  # pragma: no cover - production and tests use PostgreSQL/SQLite
            clock = func.current_timestamp()
        value = (await session.execute(select(clock))).scalar_one()
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace(" ", "T"))
        if not isinstance(value, datetime):
            raise TypeError("Database clock did not return a datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
