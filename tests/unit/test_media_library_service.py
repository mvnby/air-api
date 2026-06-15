from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import models  # noqa: F401
from models import MediaAsset, MediaProcessingJob, Product, ProductAttachment, ProductImage, Service
from services import media_library_service
from services.media_library_service import MediaLibraryService
from services.media_processing_job_service import MediaProcessingJobService


def image_bytes(size=(120, 80), color=(20, 180, 160)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def svg_bytes() -> bytes:
    return b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 80">
        <rect width="240" height="80" fill="#0f766e"/>
        <text x="24" y="52" fill="#fff">MVN</text>
    </svg>"""


def write_media_file(path, content: bytes | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content if content is not None else image_bytes(size=(64, 48)))


class FakeBackgroundProcessor:
    provider_name = "ben"

    async def process(self, *, source_content: bytes, context):
        class Result:
            content = image_bytes(size=(48, 32), color=(200, 20, 80))
            extension = "webp"
            width = 48
            height = 32

        return Result()


@pytest.fixture
async def sqlite_session(tmp_path, monkeypatch):
    monkeypatch.setattr(media_library_service, "MEDIA_LIBRARY_BASE_DIR", tmp_path / "library")
    monkeypatch.setattr(media_library_service, "MEDIA_LIBRARY_PUBLIC_PREFIX", "/media/library")

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_upload_and_list_media_assets(sqlite_session):
    response = await MediaLibraryService.upload_assets(
        session=sqlite_session,
        files=[("install-photo.png", image_bytes())],
        kind="installation",
        tags=["монтаж", "штробы"],
        created_by="admin",
    )

    assert response["uploaded"] == 1
    item = response["items"][0]
    assert item["url"].startswith("/media/library/original/")
    assert item["kind"] == "installation"
    assert item["tags"] == ["монтаж", "штробы"]
    assert item["width"] == 120
    assert item["height"] == 80

    listing = await MediaLibraryService.list_assets(
        session=sqlite_session,
        kind="installation",
        tag="монтаж",
    )
    assert listing["meta"]["total"] == 1
    assert listing["items"][0]["id"] == item["id"]


@pytest.mark.asyncio
async def test_upload_svg_media_asset_keeps_vector_source(sqlite_session):
    response = await MediaLibraryService.upload_assets(
        session=sqlite_session,
        files=[("brand-logo.svg", svg_bytes())],
        kind="brand",
        tags=["logo"],
        created_by="admin",
    )

    assert response["uploaded"] == 1
    item = response["items"][0]
    assert item["url"].startswith("/media/library/original/")
    assert item["url"].endswith(".svg")
    assert item["mime_type"] == "image/svg+xml"
    assert item["kind"] == "brand"
    assert item["tags"] == ["logo"]
    assert item["width"] == 240
    assert item["height"] == 80

    with pytest.raises(ValueError, match="SVG assets cannot be cropped"):
        await MediaLibraryService.crop_asset(
            session=sqlite_session,
            asset_id=item["id"],
            x=0,
            y=0,
            width=20,
            height=20,
            title="logo crop",
            created_by="admin",
        )


@pytest.mark.asyncio
async def test_upload_svg_media_asset_rejects_script(sqlite_session):
    with pytest.raises(ValueError, match="unsupported embedded content"):
        await MediaLibraryService.upload_assets(
            session=sqlite_session,
            files=[("unsafe.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')],
            kind="brand",
            tags=["logo"],
            created_by="admin",
        )


@pytest.mark.asyncio
async def test_upload_svg_media_asset_allows_internal_style_references(sqlite_session):
    content = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">
        <defs>
            <linearGradient id="brand"><stop offset="0" stop-color="#00a991"/></linearGradient>
        </defs>
        <rect width="16" height="16" style="fill:url(#brand)"/>
    </svg>"""

    response = await MediaLibraryService.upload_assets(
        session=sqlite_session,
        files=[("gradient-logo.svg", content)],
        kind="brand",
        tags=["logo"],
        created_by="admin",
    )

    assert response["items"][0]["mime_type"] == "image/svg+xml"


@pytest.mark.asyncio
async def test_crop_media_asset_creates_variant(sqlite_session):
    upload = await MediaLibraryService.upload_assets(
        session=sqlite_session,
        files=[("source.png", image_bytes(size=(200, 100)))],
        kind="article",
        tags=["обложка"],
        created_by="admin",
    )
    source = upload["items"][0]

    cropped = await MediaLibraryService.crop_asset(
        session=sqlite_session,
        asset_id=source["id"],
        x=20,
        y=10,
        width=60,
        height=40,
        title="source crop",
        created_by="admin",
    )

    assert cropped["parent_asset_id"] == source["id"]
    assert cropped["variant_type"] == "crop"
    assert cropped["original_url"] == source["url"]
    assert cropped["width"] == 60
    assert cropped["height"] == 40
    assert cropped["tags"] == ["обложка"]


@pytest.mark.asyncio
async def test_remove_background_uses_selected_provider(sqlite_session, monkeypatch):
    requested_providers = []

    def fake_get_processor(provider: str, *, rembg_model=None):
        requested_providers.append((provider, rembg_model))
        return FakeBackgroundProcessor()

    monkeypatch.setattr(media_library_service, "get_product_image_processor", fake_get_processor)
    upload = await MediaLibraryService.upload_assets(
        session=sqlite_session,
        files=[("source.png", image_bytes(size=(160, 120)))],
        kind="product",
        tags=["товар"],
        created_by="admin",
    )
    source = upload["items"][0]

    processed = await MediaLibraryService.remove_background(
        session=sqlite_session,
        asset_id=source["id"],
        created_by="admin",
        provider="ben",
    )

    assert requested_providers == [("ben", None)]
    assert processed["parent_asset_id"] == source["id"]
    assert processed["variant_type"] == "background_removed"
    assert processed["width"] == 48
    assert processed["height"] == 32


@pytest.mark.asyncio
async def test_upload_media_asset_from_url_uses_existing_pipeline(sqlite_session, monkeypatch):
    monkeypatch.setattr(
        MediaLibraryService,
        "_validate_remote_image_url",
        staticmethod(lambda url: url),
    )

    async def fake_download(_url: str):
        return image_bytes(size=(90, 60)), "remote-photo.png"

    monkeypatch.setattr(
        MediaLibraryService,
        "_download_remote_image",
        staticmethod(fake_download),
    )

    response = await MediaLibraryService.upload_asset_from_url(
        session=sqlite_session,
        url="https://example.com/remote-photo.png",
        kind="service",
        tags=["обслуживание"],
        created_by="admin",
    )

    assert response["uploaded"] == 1
    item = response["items"][0]
    assert item["source_filename"] == "remote-photo.png"
    assert item["kind"] == "service"
    assert item["tags"] == ["обслуживание"]
    assert item["width"] == 90
    assert item["height"] == 60


@pytest.mark.asyncio
async def test_media_processing_job_claim_and_complete_creates_media_variant(sqlite_session):
    upload = await MediaLibraryService.upload_assets(
        session=sqlite_session,
        files=[("source.png", image_bytes(size=(160, 120)))],
        kind="product",
        tags=["товар"],
        created_by="admin",
    )
    source = upload["items"][0]
    created = await MediaProcessingJobService.create_job(
        session=sqlite_session,
        source_asset_id=source["id"],
        operation="background_removal",
        provider="rembg",
        rembg_model="u2net",
        created_by="admin",
    )

    assert created["status"] == "queued"
    assert created["source_url"] == source["url"]

    claimed = await MediaProcessingJobService.claim_next_job(
        session=sqlite_session,
        worker_id="gpu-box",
        capabilities=["background_removal:rembg:u2net"],
    )

    assert claimed is not None
    assert claimed["job_id"] == created["job_id"]
    assert claimed["status"] == "running"
    assert claimed["attempts"] == 1

    completed = await MediaProcessingJobService.complete_job(
        session=sqlite_session,
        job_id=created["job_id"],
        worker_id="gpu-box",
        content=image_bytes(size=(80, 60), color=(220, 20, 80)),
        filename="processed.png",
    )

    assert completed["status"] == "success"
    assert completed["result_asset_id"] is not None
    result_asset = await sqlite_session.get(MediaAsset, completed["result_asset_id"])
    assert result_asset is not None
    assert result_asset.parent_asset_id == source["id"]
    assert result_asset.variant_type == "background_removed"
    assert result_asset.width == 80
    assert result_asset.height == 60


@pytest.mark.asyncio
async def test_media_processing_job_fail_marks_claimed_job_failed(sqlite_session):
    upload = await MediaLibraryService.upload_assets(
        session=sqlite_session,
        files=[("source.png", image_bytes(size=(160, 120)))],
        kind="product",
        tags=[],
        created_by="admin",
    )
    source = upload["items"][0]
    created = await MediaProcessingJobService.create_job(
        session=sqlite_session,
        source_asset_id=source["id"],
        operation="background_removal",
        provider="rembg",
        created_by="admin",
    )
    await MediaProcessingJobService.claim_next_job(
        session=sqlite_session,
        worker_id="gpu-box",
        capabilities=["background_removal"],
    )

    failed = await MediaProcessingJobService.fail_job(
        session=sqlite_session,
        job_id=created["job_id"],
        worker_id="gpu-box",
        error="model out of memory",
    )

    assert failed["status"] == "failed"
    assert failed["error"] == "model out of memory"
    stored_job = await sqlite_session.get(MediaProcessingJob, created["job_id"])
    assert stored_job is not None
    assert stored_job.finished_at is not None


@pytest.mark.asyncio
async def test_delete_parent_media_asset_keeps_variant(sqlite_session):
    upload = await MediaLibraryService.upload_assets(
        session=sqlite_session,
        files=[("source.png", image_bytes(size=(200, 100)))],
        kind="article",
        tags=["обложка"],
        created_by="admin",
    )
    source = upload["items"][0]
    cropped = await MediaLibraryService.crop_asset(
        session=sqlite_session,
        asset_id=source["id"],
        x=20,
        y=10,
        width=60,
        height=40,
        title="source crop",
        created_by="admin",
    )

    result = await MediaLibraryService.delete_asset(
        session=sqlite_session,
        asset_id=source["id"],
    )

    assert result["message"] == "Media asset deleted"
    listing = await MediaLibraryService.list_assets(session=sqlite_session)
    assert listing["meta"]["total"] == 1
    assert listing["items"][0]["id"] == cropped["id"]
    assert listing["items"][0]["parent_asset_id"] is None


@pytest.mark.asyncio
async def test_backfill_referenced_assets_preserves_existing_product_url(
    sqlite_session,
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    media_path = tmp_path / "media/products/shared/legacy-product.png"
    write_media_file(media_path, image_bytes(size=(64, 48)))
    product = Product(
        title="MDV Test",
        slug="mdv-test",
        price=100,
        main_image="/media/products/shared/legacy-product.png",
        images=["/media/products/shared/legacy-product.png"],
    )
    sqlite_session.add(product)
    await sqlite_session.commit()

    dry_run = await MediaLibraryService.backfill_referenced_assets(
        session=sqlite_session,
        execute=False,
        limit=20,
    )
    assert dry_run["dry_run"] is True
    assert dry_run["planned"] == 1
    assert dry_run["items"][0]["url"] == "/media/products/shared/legacy-product.png"

    executed = await MediaLibraryService.backfill_referenced_assets(
        session=sqlite_session,
        execute=True,
        limit=20,
        created_by="test",
    )
    assert executed["created"] == 1
    asset = await sqlite_session.scalar(select(MediaAsset))
    assert asset is not None
    assert asset.url == "/media/products/shared/legacy-product.png"
    assert asset.kind == "product"
    assert asset.width == 64
    assert asset.height == 48
    assert asset.created_by == "test"

    second = await MediaLibraryService.backfill_referenced_assets(
        session=sqlite_session,
        execute=True,
        limit=20,
    )
    assert second["created"] == 0
    assert second["skipped"][0]["reason"] == "already_indexed"


@pytest.mark.asyncio
async def test_backfill_referenced_assets_indexes_gallery_brand_and_service_urls(
    sqlite_session,
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    write_media_file(tmp_path / "media/products/shared/gallery.png")
    write_media_file(tmp_path / "media/services/install.png")
    product = Product(title="Gallery Product", slug="gallery-product", price=100)
    sqlite_session.add(product)
    await sqlite_session.flush()
    sqlite_session.add(
        ProductImage(product_id=product.id, url="/media/products/shared/gallery.png")
    )
    sqlite_session.add(
        Service(
            title="Монтаж",
            slug="install",
            image="/media/services/install.png",
        )
    )
    await sqlite_session.commit()

    result = await MediaLibraryService.backfill_referenced_assets(
        session=sqlite_session,
        execute=True,
        limit=20,
    )

    assert result["created"] == 2
    assets = (await sqlite_session.execute(select(MediaAsset).order_by(MediaAsset.url))).scalars().all()
    assert [asset.url for asset in assets] == [
        "/media/products/shared/gallery.png",
        "/media/services/install.png",
    ]
    assert {asset.kind for asset in assets} == {"product", "service"}


@pytest.mark.asyncio
async def test_backfill_referenced_assets_reports_missing_and_remote_urls(
    sqlite_session,
):
    product = Product(
        title="Remote Product",
        slug="remote-product",
        price=100,
        main_image="/media/products/shared/missing.png",
        images=["https://cdn.example.com/image.png"],
    )
    sqlite_session.add(product)
    await sqlite_session.commit()

    result = await MediaLibraryService.backfill_referenced_assets(
        session=sqlite_session,
        execute=False,
        limit=20,
    )

    reasons = {item["reason"] for item in result["skipped"]}
    assert {"missing_file", "remote_skipped"} <= reasons
    assert result["planned"] == 0


@pytest.mark.asyncio
async def test_usage_count_protects_service_images_and_product_attachments(
    sqlite_session,
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    image_url = "/media/services/protected.png"
    attachment_url = "/media/products/manuals/manual.pdf"
    write_media_file(tmp_path / image_url.lstrip("/"))
    product = Product(title="Protected Product", slug="protected-product", price=100)
    service = Service(title="Protected Service", slug="protected-service", image=image_url)
    sqlite_session.add(product)
    sqlite_session.add(service)
    await sqlite_session.flush()
    sqlite_session.add(
        ProductAttachment(
            product_id=product.id,
            kind="manual",
            title="Manual",
            url=attachment_url,
        )
    )
    asset = MediaAsset(
        title="Protected Service",
        kind="service",
        variant_type="original",
        url=image_url,
        original_url=image_url,
        mime_type="image/png",
        storage_provider="local",
        processing_status="ready",
    )
    sqlite_session.add(asset)
    await sqlite_session.commit()
    await sqlite_session.refresh(asset)

    assert await MediaLibraryService._usage_count(sqlite_session, image_url) == 1
    assert await MediaLibraryService._usage_count(sqlite_session, attachment_url) == 1
    with pytest.raises(ValueError, match="Media asset is used"):
        await MediaLibraryService.delete_asset(session=sqlite_session, asset_id=asset.id)
