from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from core.database import get_session
from core.security import AuthenticatedUser, get_current_auth_context
from routers.manager_catalog import router
from services.manager_catalog_service import ManagerCatalogService


@pytest.mark.asyncio
async def test_delegated_smart_search_redacts_costs_before_http_serialization(monkeypatch):
    product = {
        "id": 4, "title": "Catalog product", "slug": "catalog-product",
        "price": 1800, "old_price": None, "is_inverter": False,
        "power_cooling": None, "main_image": None, "is_published": True,
        "created_at": datetime.now(timezone.utc).isoformat(), "specs": {},
        "gallery_images": [], "manuals": [], "tags": [],
        "min_cost_byn": 900, "recommended_price_byn": 1900,
        "margin_abs_preview": 900, "margin_pct_preview": 50,
    }
    monkeypatch.setattr(ManagerCatalogService, "smart_search", AsyncMock(return_value={
        "items": [product], "meta": {"page": 1, "limit": 40, "total": 1, "pages": 1},
    }))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_auth_context] = lambda: AuthenticatedUser(
        username="collaborator", auth_source="staff_password", role="catalog_editor",
        tenant_id=2, storefront_id=20, permissions=("catalog.master.edit",),
    )
    async def session():
        yield object()
    app.dependency_overrides[get_session] = session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/manager/products/smart-search", params={"q": "product"})
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["price"] == 1800
    for field in ("min_cost_byn", "recommended_price_byn", "margin_abs_preview", "margin_pct_preview"):
        assert response.json()["items"][0].get(field) is None
