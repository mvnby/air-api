from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from core.database import get_session
from core.security import AuthenticatedUser, require_manager_access
from routers import manager_catalog_management
from services.catalog_management_service import CatalogManagementService


def _tenant_manager() -> AuthenticatedUser:
    return AuthenticatedUser(
        username="tenant-manager",
        auth_source="staff_password",
        staff_user_id=7,
        role="manager",
        tenant_id=2,
        storefront_id=20,
        tenant_membership_id=200,
        is_system_tenant=False,
    )


@pytest.mark.asyncio
async def test_catalog_management_query_requires_authentication_before_service():
    app = FastAPI()
    app.include_router(manager_catalog_management.router)
    query = AsyncMock()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(CatalogManagementService, "query", query)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post("/api/manager/catalog-management/query", json={})
    finally:
        monkeypatch.undo()

    assert response.status_code == 401
    query.assert_not_awaited()


@pytest.mark.asyncio
async def test_catalog_management_query_rejects_non_system_manager_before_service(monkeypatch):
    app = FastAPI()
    app.include_router(manager_catalog_management.router)
    app.dependency_overrides[require_manager_access] = _tenant_manager

    async def _session():
        yield object()

    app.dependency_overrides[get_session] = _session
    query = AsyncMock()
    monkeypatch.setattr(CatalogManagementService, "query", query)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/manager/catalog-management/query", json={})

    assert response.status_code == 403
    query.assert_not_awaited()
