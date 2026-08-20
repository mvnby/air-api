from io import BytesIO
import os
from pathlib import Path

import pytest
from httpx import AsyncClient
from httpx import ASGITransport
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

os.environ.setdefault("BOT_TOKEN", "test")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./manager_cleanup_api_test.db")

from core.database import get_session
from core.config import settings
from core.app_factory import create_app
from models import LegacyOwnerAuthState, Product, ProductImage, Storefront, Tenant


def _image_bytes() -> bytes:
    image = Image.new("RGB", (24, 18), (80, 140, 200))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


async def _auth_headers(async_client: AsyncClient) -> dict:
    login_resp = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    return {"Authorization": f"Bearer {login_resp.json()['access_token']}"}


@pytest.fixture
async def db(tmp_path: Path):
    db_path = tmp_path / "manager_cleanup_api.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        session.add(LegacyOwnerAuthState())
        tenant = Tenant(
            slug="mvn",
            display_name="MVN",
            kind="operator",
            status="active",
            is_system=True,
        )
        session.add(tenant)
        await session.flush()
        session.add(
            Storefront(
                tenant_id=int(tenant.id),
                slug="main",
                display_name="MVN",
                status="active",
                is_default=True,
            )
        )
        await session.commit()
        yield session

    await engine.dispose()


@pytest.fixture
async def async_client(db: AsyncSession):
    app = create_app()

    async def override_get_session():
        yield db

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_manager_main_image_cleanup_requires_auth(async_client: AsyncClient):
    response = await async_client.get("/api/manager/main-image-cleanup/items")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_manager_main_image_cleanup_rejects_unsupported_processor(
    async_client: AsyncClient,
):
    headers = await _auth_headers(async_client)

    response = await async_client.post(
        "/api/manager/main-image-cleanup/batches",
        json={"limit": 1, "processor_method": "magic_cleanup"},
        headers=headers,
    )

    assert response.status_code == 400
    assert "Unsupported cleanup processor" in response.json()["detail"]


@pytest.mark.asyncio
async def test_manager_main_image_cleanup_create_list_and_approve(
    async_client: AsyncClient,
    db,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.chdir(tmp_path)
    source_dir = tmp_path / "media/products/shared"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "api-source.png").write_bytes(_image_bytes())
    source_url = "/media/products/shared/api-source.png"
    product = Product(
        title="Cleanup API product",
        slug="cleanup-api-product",
        price=1000,
        specs={"area_m2": 20},
        main_image=source_url,
        images=[source_url],
    )
    db.add(product)
    await db.flush()
    db.add(ProductImage(product_id=product.id, url=source_url))
    await db.commit()
    await db.refresh(product)

    headers = await _auth_headers(async_client)
    create_response = await async_client.post(
        "/api/manager/main-image-cleanup/batches",
        json={"limit": 5, "processor_method": "noop"},
        headers=headers,
    )
    assert create_response.status_code == 200
    payload = create_response.json()
    assert payload["candidate_ready_count"] == 1
    item = payload["items"][0]
    assert item["status"] == "candidate_ready"
    assert item["candidate_image_url"] != source_url
    assert item["product_title"] == "Cleanup API product"
    assert item["product_slug"] == "cleanup-api-product"
    assert item["product_current_main_image"] == source_url

    list_response = await async_client.get(
        "/api/manager/main-image-cleanup/items",
        params={"batch_id": payload["batch"]["id"]},
        headers=headers,
    )
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["id"] == item["id"]
    assert list_response.json()["items"][0]["product_title"] == "Cleanup API product"

    approve_response = await async_client.post(
        "/api/manager/main-image-cleanup/items/approve",
        json={"item_ids": [item["id"]]},
        headers=headers,
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["updated_count"] == 1
    await db.refresh(product)
    assert product.main_image == item["candidate_image_url"]
    assert product.images == [source_url]
