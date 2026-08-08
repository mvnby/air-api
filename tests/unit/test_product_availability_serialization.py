from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from services.product_availability_serialization import (
    ProductAvailabilitySerialization,
)
from services.tenant_scope_service import TenantScope


def test_availability_lock_identity_is_stable_for_equivalent_phone_formats():
    scope = TenantScope(tenant_id=7, storefront_id=11)

    international = ProductAvailabilitySerialization.build_identity(
        tenant_scope=scope,
        product_id=23,
        phone="+375 (29) 111-22-33",
    )
    local = ProductAvailabilitySerialization.build_identity(
        tenant_scope=scope,
        product_id=23,
        phone="8 (029) 111-22-33",
    )

    assert international == local
    assert international.normalized_phone == "375291112233"
    assert -(2**63) <= international.lock_id < 2**63


def test_availability_lock_identity_includes_complete_scope():
    base_scope = TenantScope(tenant_id=7, storefront_id=11)
    base = ProductAvailabilitySerialization.build_identity(
        tenant_scope=base_scope,
        product_id=23,
        phone="+375291112233",
    )
    alternatives = (
        ProductAvailabilitySerialization.build_identity(
            tenant_scope=TenantScope(tenant_id=8, storefront_id=11),
            product_id=23,
            phone="+375291112233",
        ),
        ProductAvailabilitySerialization.build_identity(
            tenant_scope=TenantScope(tenant_id=7, storefront_id=12),
            product_id=23,
            phone="+375291112233",
        ),
        ProductAvailabilitySerialization.build_identity(
            tenant_scope=base_scope,
            product_id=24,
            phone="+375291112233",
        ),
        ProductAvailabilitySerialization.build_identity(
            tenant_scope=base_scope,
            product_id=23,
            phone="+375291112244",
        ),
    )

    assert all(candidate.lock_id != base.lock_id for candidate in alternatives)


@pytest.mark.asyncio
async def test_postgres_claim_takes_transaction_lock_before_database_clock():
    database_now = datetime(2026, 8, 1, 12, 30, tzinfo=timezone.utc)

    class ScalarResult:
        def scalar_one(self):
            return database_now

    class FakeSession:
        def __init__(self):
            self.calls = []

        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        async def execute(self, statement, parameters=None):
            self.calls.append((str(statement), parameters))
            return ScalarResult()

    session = FakeSession()
    scope = TenantScope(tenant_id=7, storefront_id=11)

    claim = await ProductAvailabilitySerialization.acquire(
        session,  # type: ignore[arg-type]
        tenant_scope=scope,
        product_id=23,
        phone="+375 (29) 111-22-33",
    )

    assert "pg_advisory_xact_lock" in session.calls[0][0]
    assert session.calls[0][1] == {"lock_id": claim.identity.lock_id}
    assert "clock_timestamp" in session.calls[1][0]
    assert claim.database_now == database_now
