from dataclasses import FrozenInstanceError
from unittest.mock import AsyncMock

import pytest
from sqlmodel import select

from crud.tenancy import TenantScopeRow
from models import Order
from services.tenant_scope_service import (
    SystemTenantScopeResolver,
    TenantScope,
    TenantScopeResolutionError,
    storefront_or_fully_legacy_scope_clause,
    tenant_or_fully_legacy_scope_clause,
)


@pytest.mark.asyncio
async def test_resolve_system_scope_returns_immutable_server_scope(monkeypatch):
    session = object()
    resolver = AsyncMock(return_value=[TenantScopeRow(tenant_id=11, storefront_id=21)])
    monkeypatch.setattr(
        "services.tenant_scope_service.TenancyDAO.list_active_system_scope_candidates",
        resolver,
    )

    scope = await SystemTenantScopeResolver.resolve(session)

    assert scope.tenant_id == 11
    assert scope.storefront_id == 21
    with pytest.raises(FrozenInstanceError):
        scope.tenant_id = 99  # type: ignore[misc]
    resolver.assert_awaited_once_with(
        session,
        tenant_slug="mvn",
        storefront_slug="main",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "candidates",
    [
        [],
        [
            TenantScopeRow(tenant_id=11, storefront_id=21),
            TenantScopeRow(tenant_id=12, storefront_id=22),
        ],
    ],
)
async def test_resolve_system_scope_fails_closed_when_missing_or_ambiguous(monkeypatch, candidates):
    resolver = AsyncMock(return_value=candidates)
    monkeypatch.setattr(
        "services.tenant_scope_service.TenancyDAO.list_active_system_scope_candidates",
        resolver,
    )

    with pytest.raises(TenantScopeResolutionError, match="Canonical system tenant scope is unavailable"):
        await SystemTenantScopeResolver.resolve(object())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "candidate",
    [
        TenantScopeRow(tenant_id=0, storefront_id=21),
        TenantScopeRow(tenant_id=11, storefront_id=0),
    ],
)
async def test_resolve_system_scope_rejects_invalid_database_ids(monkeypatch, candidate):
    resolver = AsyncMock(return_value=[candidate])
    monkeypatch.setattr(
        "services.tenant_scope_service.TenancyDAO.list_active_system_scope_candidates",
        resolver,
    )

    with pytest.raises(TenantScopeResolutionError, match="Canonical system tenant scope is invalid"):
        await SystemTenantScopeResolver.resolve(object())


@pytest.mark.asyncio
async def test_tenant_scope_legacy_clause_rejects_partially_scoped_rows(db, tenant_scope):
    current = Order(
        title="Current scope",
        tenant_id=tenant_scope.tenant_id,
        storefront_id=tenant_scope.storefront_id,
    )
    current_tenant_without_storefront = Order(
        title="Current tenant pending storefront backfill",
        tenant_id=tenant_scope.tenant_id,
        storefront_id=None,
    )
    fully_legacy = Order(title="Fully legacy")
    partial_legacy = Order(
        title="Unsafe partial legacy",
        tenant_id=None,
        storefront_id=tenant_scope.storefront_id,
    )
    db.add_all(
        [
            current,
            current_tenant_without_storefront,
            fully_legacy,
            partial_legacy,
        ]
    )
    await db.commit()

    matches = (
        await db.execute(
            select(Order).where(
                tenant_or_fully_legacy_scope_clause(Order, tenant_scope)
            )
        )
    ).scalars().all()

    assert {order.title for order in matches} == {
        "Current scope",
        "Current tenant pending storefront backfill",
        "Fully legacy",
    }


@pytest.mark.asyncio
async def test_storefront_scope_legacy_clause_requires_exact_or_fully_null_pair(
    db,
    tenant_scope,
):
    exact = Order(
        title="Exact storefront",
        tenant_id=tenant_scope.tenant_id,
        storefront_id=tenant_scope.storefront_id,
    )
    fully_legacy = Order(title="Fully legacy storefront")
    missing_storefront = Order(
        title="Missing storefront",
        tenant_id=tenant_scope.tenant_id,
        storefront_id=None,
    )
    missing_tenant = Order(
        title="Missing tenant",
        tenant_id=None,
        storefront_id=tenant_scope.storefront_id,
    )
    db.add_all([exact, fully_legacy, missing_storefront, missing_tenant])
    await db.commit()

    matches = (
        await db.execute(
            select(Order).where(
                storefront_or_fully_legacy_scope_clause(Order, tenant_scope)
            )
        )
    ).scalars().all()

    assert {order.title for order in matches} == {
        "Exact storefront",
        "Fully legacy storefront",
    }
