from dataclasses import FrozenInstanceError
from unittest.mock import AsyncMock

import pytest
from sqlmodel import select

from crud.tenancy import TenantScopeRow
from models import Customer, CustomerType, Order, Storefront, Tenant
from services.tenant_scope_service import (
    SystemTenantScopeResolver,
    TenantScope,
    TenantScopeResolutionError,
    storefront_scope_clause,
    tenant_scope_clause,
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
    assert scope.is_system is True
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
async def test_tenant_scope_clause_requires_exact_tenant(db, tenant_scope):
    foreign_tenant = Tenant(
        id=2,
        slug="foreign",
        display_name="Foreign",
        status="active",
        is_system=False,
    )
    db.add(foreign_tenant)
    await db.flush()
    foreign_storefront = Storefront(
        id=2,
        tenant_id=int(foreign_tenant.id),
        slug="main",
        display_name="Foreign main",
        status="active",
        is_default=True,
    )
    db.add(foreign_storefront)
    await db.flush()

    current = Order(
        title="Current scope",
        tenant_id=tenant_scope.tenant_id,
        storefront_id=tenant_scope.storefront_id,
    )
    foreign = Order(
        title="Foreign scope",
        tenant_id=int(foreign_tenant.id),
        storefront_id=int(foreign_storefront.id),
    )
    db.add_all([current, foreign])
    await db.commit()

    matches = (
        await db.execute(
            select(Order).where(
                tenant_scope_clause(Order, tenant_scope)
            )
        )
    ).scalars().all()

    assert [order.title for order in matches] == ["Current scope"]


@pytest.mark.asyncio
async def test_storefront_scope_clause_requires_exact_pair(
    db,
    tenant_scope,
):
    secondary = Storefront(
        id=2,
        tenant_id=tenant_scope.tenant_id,
        slug="secondary",
        display_name="Secondary",
        status="active",
        is_default=False,
    )
    db.add(secondary)
    await db.flush()
    exact = Order(
        title="Exact storefront",
        tenant_id=tenant_scope.tenant_id,
        storefront_id=tenant_scope.storefront_id,
    )
    other_storefront = Order(
        title="Other storefront",
        tenant_id=tenant_scope.tenant_id,
        storefront_id=int(secondary.id),
    )
    db.add_all([exact, other_storefront])
    await db.commit()

    matches = (
        await db.execute(
            select(Order).where(
                storefront_scope_clause(Order, tenant_scope)
            )
        )
    ).scalars().all()

    assert [order.title for order in matches] == ["Exact storefront"]


@pytest.mark.asyncio
async def test_scope_clause_does_not_grant_system_tenant_special_access(db):
    foreign_tenant = Tenant(
        id=2,
        slug="foreign-system-test",
        display_name="Foreign",
        status="active",
        is_system=False,
    )
    db.add(foreign_tenant)
    await db.flush()
    foreign_storefront = Storefront(
        id=2,
        tenant_id=int(foreign_tenant.id),
        slug="main",
        display_name="Foreign main",
        status="active",
        is_default=True,
    )
    db.add(foreign_storefront)
    await db.flush()
    foreign_scope = TenantScope(
        tenant_id=int(foreign_tenant.id),
        storefront_id=int(foreign_storefront.id),
        is_system=False,
    )
    system_order = Order(
        title="System order",
        tenant_id=1,
        storefront_id=1,
    )
    system_customer = Customer(
        tenant_id=1,
        name="System customer",
        phone="+375290000099",
        type=CustomerType.individual,
    )
    db.add_all([system_order, system_customer])
    await db.commit()

    order_matches = (
        await db.execute(
            select(Order).where(
                tenant_scope_clause(Order, foreign_scope)
            )
        )
    ).scalars().all()
    customer_matches = (
        await db.execute(
            select(Customer).where(
                tenant_scope_clause(
                    Customer,
                    foreign_scope,
                )
            )
        )
    ).scalars().all()

    assert order_matches == []
    assert customer_matches == []
