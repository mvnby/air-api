from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel import select

from crud.catalog_revision import CatalogRevisionDAO
from models import (
    Brand,
    ImportMediaCache,
    IntegrationOutboxEvent,
    Product,
    ProductAttachment,
    Storefront,
    Tenant,
)
from services.catalog_invalidation_contracts import (
    CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT,
)
from services.catalog_revision_service import CatalogRevisionService
from services.importer_service import ImporterService, _should_replace_imported_main_image


def _png_bytes(color=(40, 80, 160)) -> bytes:
    image = Image.new("RGB", (12, 12), color)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_importer_replaces_only_empty_or_remote_main_images():
    assert _should_replace_imported_main_image(None) is True
    assert _should_replace_imported_main_image("") is True
    assert _should_replace_imported_main_image("https://mdv-aircond.ru/upload/source.png") is True
    assert _should_replace_imported_main_image("https://example.com/source.png") is True
    assert _should_replace_imported_main_image("/media/products/shared/source.webp") is False
    assert _should_replace_imported_main_image("media/products/shared/source.webp") is False
    assert _should_replace_imported_main_image("https://cdn.mvn.by/products/shared/source.webp") is False


class _FakeResponse:
    def __init__(self, *, status_code: int, content: bytes, url: str):
        self.status_code = status_code
        self.content = content
        self.url = url


class _FakeSessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.fixture
async def sqlite_session(tmp_path: Path):
    db_path = tmp_path / "importer_media_manuals.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_importer_saves_manuals_and_reuses_image_cache_on_update(sqlite_session, monkeypatch):
    sqlite_session.add(
        Tenant(
            id=1,
            slug="system",
            display_name="System",
            status="active",
            is_system=True,
        )
    )
    await sqlite_session.flush()
    sqlite_session.add(
        Storefront(
            id=1,
            tenant_id=1,
            slug="main",
            display_name="Main",
            status="active",
            is_default=True,
        )
    )
    await sqlite_session.commit()

    image_calls = {"count": 0}

    class _FakeClient:
        def __init__(self, *args, **kwargs):  # noqa: ARG002
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url):
            image_calls["count"] += 1
            return _FakeResponse(
                status_code=200,
                content=_png_bytes(),
                url=url,
            )

    class _FakeParser:
        async def parse(self, url):  # noqa: ARG002
            return {
                "title": "LG Test Import",
                "slug": "lg-test-import",
                "description": "Test description",
                "price": 1234,
                "area": 25,
                "main_image": "https://img.example.com/lg-test-import.png",
                "images": [],
                "save_gallery": True,
                "categories": [],
                "specs": {"Бренд": "LG", "Тип": "сплит-система"},
                "metrics": {"area": 25, "is_inverter": True, "power_cooling": 2.6},
                "related_urls": [],
                "manuals": [
                    {
                        "kind": "manual",
                        "title": "Руководство пользователя",
                        "url": "https://img.example.com/manual.pdf",
                        "source": "lg24",
                    }
                ],
            }

    monkeypatch.setattr("services.import_media_service.httpx.AsyncClient", _FakeClient)
    monkeypatch.setattr(
        "services.importer_service.async_session_maker",
        lambda: _FakeSessionContext(sqlite_session),
    )

    service = ImporterService()
    service.get_parser = lambda url: _FakeParser()  # noqa: ARG005

    first = await service.import_product(
        "https://example.com/product/lg-test-import",
        update_existing=False,
        collect_related=False,
    )
    revision_after_first = await CatalogRevisionDAO.get_current(sqlite_session)
    events_after_first = (
        await sqlite_session.execute(
            select(IntegrationOutboxEvent).where(
                IntegrationOutboxEvent.event_type
                == CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT
            )
        )
    ).scalars().all()
    second = await service.import_product(
        "https://example.com/product/lg-test-import",
        update_existing=True,
        collect_related=False,
    )

    assert first["product"].id == second["product"].id
    assert image_calls["count"] == 1
    revision_after_second = await CatalogRevisionDAO.get_current(sqlite_session)
    events_after_second = (
        await sqlite_session.execute(
            select(IntegrationOutboxEvent).where(
                IntegrationOutboxEvent.event_type
                == CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT
            )
        )
    ).scalars().all()
    assert revision_after_first.revision == 1
    assert revision_after_second.revision == 1
    assert len(events_after_first) == 1
    assert len(events_after_second) == 1
    assert events_after_second[0].payload["reason"] == "product_import"

    brand = (
        await sqlite_session.execute(select(Brand).where(Brand.slug == "lg"))
    ).scalar_one()
    brand.title = ""
    sqlite_session.add(brand)
    await sqlite_session.commit()

    third = await service.import_product(
        "https://example.com/product/lg-test-import",
        update_existing=True,
        collect_related=False,
    )
    revision_after_self_heal = await CatalogRevisionDAO.get_current(sqlite_session)
    events_after_self_heal = (
        await sqlite_session.execute(
            select(IntegrationOutboxEvent).where(
                IntegrationOutboxEvent.event_type
                == CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT
            )
        )
    ).scalars().all()
    await sqlite_session.refresh(brand)
    assert third["product"].id == first["product"].id
    assert brand.title == "LG"
    assert revision_after_self_heal.revision == 2
    assert len(events_after_self_heal) == 2
    assert events_after_self_heal[-1].payload["reason"] == "product_import"
    assert image_calls["count"] == 1

    product = (await sqlite_session.execute(select(Product).where(Product.slug == "lg-test-import"))).scalar_one()
    assert product.main_image
    assert product.main_image.startswith("/media/products/shared/")

    manuals = (
        await sqlite_session.execute(
            select(ProductAttachment).where(
                ProductAttachment.product_id == product.id,
                ProductAttachment.kind == "manual",
            )
        )
    ).scalars().all()
    assert len(manuals) == 1
    assert manuals[0].url == "https://img.example.com/manual.pdf"

    cache_rows = (await sqlite_session.execute(select(ImportMediaCache))).scalars().all()
    assert len(cache_rows) == 1


@pytest.mark.asyncio
async def test_importer_propagates_required_media_errors(sqlite_session, monkeypatch):
    calls = []

    class _FakeParser:
        async def parse(self, url):  # noqa: ARG002
            return {
                "title": "MDV Required Media",
                "slug": "mdv-required-media",
                "description": "Test description",
                "price": 1234,
                "area": 25,
                "main_image": "https://mdv-aircond.ru/upload/required.png",
                "images": [],
                "save_gallery": True,
                "require_media_download": True,
                "categories": [],
                "specs": {"brand": "MDV", "type": "сплит-система"},
                "metrics": {"area": 25, "is_inverter": True, "power_cooling": 2.6},
                "related_urls": [],
            }

    async def fake_resolve_or_download(*args, **kwargs):  # noqa: ARG001
        calls.append(kwargs)
        raise RuntimeError("PutObject Unauthorized")

    monkeypatch.setattr(
        "services.importer_service.async_session_maker",
        lambda: _FakeSessionContext(sqlite_session),
    )
    monkeypatch.setattr(
        "services.importer_service.ImportMediaService.resolve_or_download",
        fake_resolve_or_download,
    )

    service = ImporterService()
    service.get_parser = lambda url: _FakeParser()  # noqa: ARG005

    with pytest.raises(RuntimeError, match="PutObject Unauthorized"):
        await service.import_product(
            "https://mdv-aircond.ru/catalog/test",
            update_existing=False,
            collect_related=False,
        )

    assert calls
    assert calls[0]["raise_on_error"] is True
    product = (
        await sqlite_session.execute(
            select(Product).where(Product.slug == "mdv-required-media")
        )
    ).scalar_one_or_none()
    assert product is None


@pytest.mark.asyncio
async def test_importer_rolls_back_product_when_invalidation_staging_fails(
    tmp_path,
    monkeypatch,
):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'importer_atomicity.db'}",
        echo=False,
    )
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    session_factory = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    class _FakeParser:
        async def parse(self, url):  # noqa: ARG002
            return {
                "title": "Atomic Import",
                "slug": "atomic-import",
                "description": "Must roll back",
                "price": 1500,
                "main_image": None,
                "images": [],
                "save_gallery": False,
                "categories": [],
                "specs": {"brand": "LG", "type": "сплит-система"},
                "metrics": {"area": 25, "is_inverter": True},
                "related_urls": [],
            }

    monkeypatch.setattr("services.importer_service.async_session_maker", session_factory)
    monkeypatch.setattr(
        CatalogRevisionService,
        "stage_invalidation",
        AsyncMock(side_effect=RuntimeError("outbox unavailable")),
    )
    service = ImporterService()
    service.get_parser = lambda url: _FakeParser()  # noqa: ARG005

    with pytest.raises(RuntimeError, match="outbox unavailable"):
        await service.import_product("https://example.com/atomic-import")

    async with session_factory() as verification_session:
        assert (
            await verification_session.execute(
                select(Product).where(Product.slug == "atomic-import")
            )
        ).scalar_one_or_none() is None
        assert (
            await CatalogRevisionDAO.get_current(verification_session)
        ).revision == 0
        assert (
            await verification_session.execute(select(IntegrationOutboxEvent))
        ).scalars().all() == []

    await engine.dispose()
