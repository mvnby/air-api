from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from core.app_static import mount_manager_assets
from routers.manager_spa import create_manager_spa_router


@pytest.fixture()
async def manager_client(tmp_path: Path):
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text('<script src="/manager/assets/index-test.js"></script>')
    (assets / "index-test.js").write_text("import('./OrdersKanbanView-test.js')")
    (assets / "OrdersKanbanView-test.js").write_text("export default {}")
    (assets / "index-test.css").write_text("body{}")
    (assets / "logo.svg").write_text("<svg></svg>")

    app = FastAPI()
    mount_manager_assets(app, dist)
    app.include_router(create_manager_spa_router(dist))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_manager_index_disables_cache(manager_client):
    response = await manager_client.get("/manager/")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate, max-age=0"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["expires"] == "0"


@pytest.mark.asyncio
async def test_manager_js_and_css_chunks_disable_cache(manager_client):
    js_response = await manager_client.get("/manager/assets/index-test.js")
    css_response = await manager_client.get("/manager/assets/index-test.css")

    assert js_response.status_code == 200
    assert css_response.status_code == 200
    assert js_response.headers["cache-control"] == "no-store, no-cache, must-revalidate, max-age=0"
    assert css_response.headers["cache-control"] == "no-store, no-cache, must-revalidate, max-age=0"


@pytest.mark.asyncio
async def test_manager_other_assets_keep_default_cache_headers(manager_client):
    response = await manager_client.get("/manager/assets/logo.svg")

    assert response.status_code == 200
    assert "cache-control" not in response.headers
