import hashlib
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel import select

from models import ImportMediaCache
from services.media_storage_service import StoredMediaObject
from services.import_media_service import ImportMediaService


def _png_bytes(color: tuple[int, int, int] = (20, 120, 200)) -> bytes:
    image = Image.new("RGB", (8, 8), color)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class _FakeResponse:
    def __init__(self, *, status_code: int, content: bytes, url: str):
        self.status_code = status_code
        self.content = content
        self.url = url


class _FakeOriginalSourceStorage:
    provider_name = "fake_local"

    def __init__(self):
        self.calls = []

    def build_product_original_object(
        self,
        *,
        content_hash: str,
        extension: str = "webp",
    ) -> StoredMediaObject:
        return StoredMediaObject(
            url=f"/media/products/shared/{content_hash}.{extension}",
            content_hash=content_hash,
            storage_provider=self.provider_name,
            path=f"media/products/shared/{content_hash}.{extension}",
        )

    async def save_product_original(
        self,
        *,
        content: bytes,
        extension: str = "webp",
    ) -> StoredMediaObject:
        self.calls.append({"content": content, "extension": extension})
        content_hash = hashlib.sha256(content).hexdigest()
        return self.build_product_original_object(
            content_hash=content_hash,
            extension=extension,
        )


@pytest.fixture
async def sqlite_session(tmp_path: Path):
    db_path = tmp_path / "import_media_test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_import_media_service_reuses_cached_url(sqlite_session, monkeypatch):
    monkeypatch.chdir(Path(sqlite_session.bind.url.database).parent)
    calls = {"count": 0}

    class _FakeClient:
        def __init__(self, *args, **kwargs):  # noqa: ARG002
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url):
            calls["count"] += 1
            return _FakeResponse(
                status_code=200,
                content=_png_bytes(),
                url=url,
            )

    monkeypatch.setattr("services.import_media_service.httpx.AsyncClient", _FakeClient)

    first = await ImportMediaService.resolve_or_download(
        sqlite_session,
        source_url="https://example.com/image-1.png#fragment",
    )
    await sqlite_session.commit()
    second = await ImportMediaService.resolve_or_download(
        sqlite_session,
        source_url="https://example.com/image-1.png",
    )
    await sqlite_session.commit()

    assert first
    assert second == first
    assert calls["count"] == 1

    rows = (
        await sqlite_session.execute(
            select(ImportMediaCache).where(ImportMediaCache.source_url == "https://example.com/image-1.png")
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].local_url == first


@pytest.mark.asyncio
async def test_import_media_service_dedupes_same_content_for_different_urls(sqlite_session, monkeypatch):
    monkeypatch.chdir(Path(sqlite_session.bind.url.database).parent)
    calls = {"count": 0}

    class _FakeClient:
        def __init__(self, *args, **kwargs):  # noqa: ARG002
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url):
            calls["count"] += 1
            return _FakeResponse(
                status_code=200,
                content=_png_bytes((10, 200, 20)),
                url=url,
            )

    monkeypatch.setattr("services.import_media_service.httpx.AsyncClient", _FakeClient)

    first = await ImportMediaService.resolve_or_download(sqlite_session, source_url="https://example.com/image-a.png")
    second = await ImportMediaService.resolve_or_download(sqlite_session, source_url="https://cdn.example.com/image-b.png")
    await sqlite_session.commit()

    assert first
    assert second
    assert first == second
    assert calls["count"] == 2

    rows = (await sqlite_session.execute(select(ImportMediaCache))).scalars().all()
    assert len(rows) == 2
    assert rows[0].local_url == rows[1].local_url


@pytest.mark.asyncio
async def test_import_media_service_writes_download_through_original_source_storage(
    sqlite_session,
    monkeypatch,
):
    fake_storage = _FakeOriginalSourceStorage()

    class _FakeClient:
        def __init__(self, *args, **kwargs):  # noqa: ARG002
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url):
            return _FakeResponse(
                status_code=200,
                content=_png_bytes((200, 80, 20)),
                url=url,
            )

    monkeypatch.setattr("services.import_media_service.httpx.AsyncClient", _FakeClient)

    first = await ImportMediaService.resolve_or_download(
        sqlite_session,
        source_url="https://example.com/provider-aware.png",
        source_storage=fake_storage,
    )
    await sqlite_session.commit()
    second = await ImportMediaService.resolve_or_download(
        sqlite_session,
        source_url="https://example.com/provider-aware.png",
        source_storage=fake_storage,
    )
    await sqlite_session.commit()

    assert first
    assert second == first
    assert first.startswith("/media/products/shared/")
    assert len(fake_storage.calls) == 1
    assert fake_storage.calls[0]["extension"] == "webp"

    cache_row = (
        await sqlite_session.execute(
            select(ImportMediaCache).where(
                ImportMediaCache.source_url == "https://example.com/provider-aware.png"
            )
        )
    ).scalar_one()
    assert cache_row.local_url == first
