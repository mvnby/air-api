from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel import select

from models import ImportMediaCache, Product, ProductAttachment
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
    second = await service.import_product(
        "https://example.com/product/lg-test-import",
        update_existing=True,
        collect_related=False,
    )

    assert first["product"].id == second["product"].id
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
