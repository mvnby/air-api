from __future__ import annotations

import hashlib

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from models import IntegrationOutboxEvent, Product, ProductImage, ProductImageVariant
from services.media_storage_service import S3CompatibleProductOriginalSourceStorage
from services.product_media_url_backfill_download import DownloadedProductMedia
from services.product_media_url_backfill_manifest import ProductMediaUrlBackfillManifest
from services.product_media_url_backfill_plan_token import ProductMediaUrlBackfillBlockedError
from services.product_media_url_backfill_service import ProductMediaUrlBackfillService


OLD_URL = "/media/products/shared/legacy.webp"
TARGET_URL = "https://cdn.mvn.by/products/variants/original/legacy.webp"
CONTENT = b"same-reviewed-image-content"


class FakeS3Client:
    def put_object(self, **_kwargs):
        raise AssertionError("reuse plan must not write storage")


class FakeDownloader:
    async def download(self, url: str, *, allowed_hosts: tuple[str, ...]):
        assert allowed_hosts
        return DownloadedProductMedia(
            source_url=url,
            final_url=url,
            content_type="image/webp",
            content=CONTENT,
            content_hash=hashlib.sha256(CONTENT).hexdigest(),
            width=10,
            height=10,
        )


def _storage() -> S3CompatibleProductOriginalSourceStorage:
    return S3CompatibleProductOriginalSourceStorage(
        provider_name="r2",
        bucket="test",
        endpoint_url="https://example.r2.cloudflarestorage.com",
        public_base_url="https://cdn.mvn.by",
        access_key_id="test",
        secret_access_key="test",
        key_prefix="products/shared",
        client=FakeS3Client(),
    )


def _public_audit(*, matches: bool) -> dict:
    return {
        "product_count": 2,
        "snapshot_sha256": "a" * 64 if matches else "f" * 64,
        "blocked_field_count": 3 if matches else 0,
        "blocked_product_count": 1 if matches else 0,
        "blocked": [],
        "expected_product_count": 2,
        "expected_snapshot_sha256": "a" * 64,
        "snapshot_matches": matches,
        "manifest_source_count": 1,
        "unmatched_blocked_urls": [],
        "source_product_drift": [] if matches else [{"old_url": OLD_URL}],
    }


async def _seed(db: AsyncSession) -> tuple[Product, Product]:
    selected = Product(
        title="Selected",
        slug="media-backfill-selected",
        price=1000,
        is_published=True,
        main_image=OLD_URL,
        images=[OLD_URL],
    )
    already_public = Product(
        title="Already public through another variant",
        slug="media-backfill-not-selected",
        price=1000,
        is_published=True,
        main_image=OLD_URL,
        images=[OLD_URL],
    )
    db.add_all([selected, already_public])
    await db.flush()
    image = ProductImage(product_id=int(selected.id), url=OLD_URL)
    db.add(image)
    await db.flush()
    db.add(
        ProductImageVariant(
            product_image_id=int(image.id),
            variant_type="original",
            url=OLD_URL,
            processing_status="ready",
        )
    )
    await db.flush()
    return selected, already_public


def _manifest(
    *,
    selected_id: int,
    db_snapshot_sha256: str,
) -> ProductMediaUrlBackfillManifest:
    return ProductMediaUrlBackfillManifest.normalize(
        {
            "version": 1,
            "name": "postgres-reuse-test",
            "public_catalog_url": "https://api.mvn.by/api/v1/products",
            "expected_public_product_count": 2,
            "expected_public_snapshot_sha256": "a" * 64,
            "expected_db_snapshot_sha256": db_snapshot_sha256,
            "sources": [
                {
                    "old_url": OLD_URL,
                    "action": "reuse",
                    "expected_product_ids": [selected_id],
                    "target_url": TARGET_URL,
                }
            ],
        }
    )


@pytest.mark.asyncio
async def test_exact_plan_updates_only_reviewed_product_and_is_idempotent(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected, already_public = await _seed(db)
    state = await ProductMediaUrlBackfillService._load_state(db, for_update=False)
    manifest = _manifest(
        selected_id=int(selected.id),
        db_snapshot_sha256=ProductMediaUrlBackfillService._db_snapshot_hash(state.products),
    )

    async def current_audit(*_args, **_kwargs):
        return _public_audit(matches=True)

    monkeypatch.setattr(
        ProductMediaUrlBackfillService,
        "audit_public",
        current_audit,
    )
    plan = await ProductMediaUrlBackfillService.plan(
        db,
        manifest=manifest,
        downloader=FakeDownloader(),
        source_storage=_storage(),
    )
    assert plan["ready"] is True
    assert plan["product_count"] == 1
    assert plan["location_count"] == 4
    result = await ProductMediaUrlBackfillService.execute(
        db,
        manifest=manifest,
        plan_token=plan["plan_token"],
        downloader=FakeDownloader(),
        source_storage=_storage(),
    )
    assert result["changed"] is True
    assert result["changed_product_count"] == 1
    assert result["changed_location_count"] == 4
    await db.flush()
    await db.refresh(selected)
    await db.refresh(already_public)
    assert selected.main_image == TARGET_URL
    assert selected.images == [TARGET_URL]
    assert already_public.main_image == OLD_URL
    image = await db.scalar(
        select(ProductImage).where(ProductImage.product_id == selected.id)
    )
    variant = await db.scalar(
        select(ProductImageVariant).where(
            ProductImageVariant.product_image_id == image.id
        )
    )
    assert image.url == TARGET_URL
    assert variant.url == TARGET_URL
    assert await db.scalar(select(IntegrationOutboxEvent)) is not None

    async def completed_audit(*_args, **_kwargs):
        return _public_audit(matches=False)

    monkeypatch.setattr(
        ProductMediaUrlBackfillService,
        "audit_public",
        completed_audit,
    )
    no_op_plan = await ProductMediaUrlBackfillService.plan(
        db,
        manifest=manifest,
        downloader=FakeDownloader(),
        source_storage=_storage(),
    )
    assert no_op_plan["ready"] is True
    assert no_op_plan["complete"] is True
    no_op = await ProductMediaUrlBackfillService.execute(
        db,
        manifest=manifest,
        plan_token=no_op_plan["plan_token"],
        downloader=FakeDownloader(),
        source_storage=_storage(),
    )
    assert no_op == {
        "mode": "execute",
        "changed": False,
        "complete": True,
        "reviewed_plan_digest": no_op_plan["plan_digest"],
        "changed_product_count": 0,
        "changed_location_count": 0,
        "changes": [],
        "source_evidence": no_op_plan["source_evidence"],
    }


@pytest.mark.asyncio
async def test_postgresql_primary_advisory_lock_serializes_execution(db_engine) -> None:
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as holder, factory() as contender:
        await ProductMediaUrlBackfillService._require_primary_and_lock(holder)
        with pytest.raises(ProductMediaUrlBackfillBlockedError, match="Another"):
            await ProductMediaUrlBackfillService._require_primary_and_lock(contender)
        await contender.rollback()
        await holder.rollback()
