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
    for filename in (
        "index-Gi6DkFoB.js",
        "EnvelopeBrandingFields-CfJ87O0_.js",
        "check-0vqBvP-3.js",
        "useCatalogAccess-BLNojPl-.js",
        "OrderDocumentsWorkspace-BUidKi-p.css",
        "digits-12345678.js",
        "index-1234567.js",
        "index-123456789.js",
        "index-Gi6DkFoB.js.map",
        "logo-Gi6DkFoB.svg",
    ):
        (assets / filename).write_text("test build asset")

    app = FastAPI()
    mount_manager_assets(app, dist)
    app.include_router(create_manager_spa_router(dist))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/manager", "/manager/", "/manager/orders/279"])
async def test_manager_index_disables_cache(manager_client, path):
    response = await manager_client.get(path)

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


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "HEAD"])
@pytest.mark.parametrize(
    "filename",
    [
        "index-Gi6DkFoB.js",
        "EnvelopeBrandingFields-CfJ87O0_.js",
        "check-0vqBvP-3.js",
        "useCatalogAccess-BLNojPl-.js",
        "OrderDocumentsWorkspace-BUidKi-p.css",
        "digits-12345678.js",
    ],
)
async def test_manager_hashed_build_assets_are_immutable(manager_client, method, filename):
    response = await manager_client.request(method, f"/manager/assets/{filename}")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert "pragma" not in response.headers
    assert "expires" not in response.headers


@pytest.mark.asyncio
@pytest.mark.parametrize("validator", ["etag", "last-modified"])
async def test_manager_hashed_asset_revalidation_keeps_immutable_policy(manager_client, validator):
    url = "/manager/assets/index-Gi6DkFoB.js"
    initial = await manager_client.get(url)
    conditional_header = "if-none-match" if validator == "etag" else "if-modified-since"

    response = await manager_client.get(url, headers={conditional_header: initial.headers[validator]})

    assert response.status_code == 304
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


@pytest.mark.asyncio
async def test_manager_hashed_partial_asset_is_immutable(manager_client):
    response = await manager_client.get(
        "/manager/assets/index-Gi6DkFoB.js", headers={"range": "bytes=0-3"}
    )

    assert response.status_code == 206
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "headers", "status"),
    [
        ("GET", "/manager/assets/missing-Gi6DkFoB.js", {}, 404),
        ("GET", "/manager/assets/missing-BUidKi-p.css", {}, 404),
        ("POST", "/manager/assets/index-Gi6DkFoB.js", {}, 405),
        ("GET", "/manager/assets/index-Gi6DkFoB.js", {"range": "bytes=999-"}, 416),
    ],
)
async def test_manager_asset_errors_are_not_immutable(manager_client, method, path, headers, status):
    response = await manager_client.request(method, path, headers=headers)

    assert response.status_code == status
    assert "immutable" not in response.headers.get("cache-control", "")
    assert "max-age=31536000" not in response.headers.get("cache-control", "")
    if status == 404:
        assert "no-store" in response.headers["cache-control"]


@pytest.mark.asyncio
@pytest.mark.parametrize("filename", ["index-1234567.js", "index-123456789.js"])
async def test_manager_assets_without_vite_hash_keep_no_cache(manager_client, filename):
    response = await manager_client.get(f"/manager/assets/{filename}")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate, max-age=0"


@pytest.mark.asyncio
@pytest.mark.parametrize("filename", ["index-Gi6DkFoB.js.map", "logo-Gi6DkFoB.svg"])
async def test_manager_non_build_assets_keep_default_cache_headers(manager_client, filename):
    response = await manager_client.get(f"/manager/assets/{filename}")

    assert response.status_code == 200
    assert "cache-control" not in response.headers
