import hashlib
from pathlib import Path

import pytest

from services.media_storage_service import (
    LocalProductMediaStorage,
    S3CompatibleProductMediaStorage,
    get_product_media_storage,
)
from services.product_image_processing_contract import ProductImageVariantType


class FakeS3Client:
    def __init__(self):
        self.calls = []

    def put_object(self, **kwargs):
        self.calls.append(kwargs)


def test_local_storage_builds_existing_fallback_url(tmp_path: Path):
    storage = LocalProductMediaStorage(base_dir=tmp_path / "media/products/variants")
    content_hash = "a" * 64

    target = storage.build_product_variant_object(
        content_hash=content_hash,
        variant_type=ProductImageVariantType.CARD.value,
        extension="webp",
    )

    assert target.storage_provider == "local"
    assert target.url == f"/media/products/variants/card/{content_hash}.webp"
    assert target.path.endswith(f"media/products/variants/card/{content_hash}.webp")


@pytest.mark.asyncio
async def test_s3_storage_uses_content_addressed_r2_key_and_cache_headers():
    fake_client = FakeS3Client()
    storage = S3CompatibleProductMediaStorage(
        provider_name="r2",
        bucket="mvn-media",
        endpoint_url="https://example-account.r2.cloudflarestorage.com",
        public_base_url="https://cdn.mvn.by/media",
        key_prefix="products/variants",
        cache_control="public, max-age=31536000, immutable",
        client=fake_client,
    )
    content = b"image-bytes"
    content_hash = hashlib.sha256(content).hexdigest()

    planned = storage.build_product_variant_object(
        content_hash=content_hash,
        variant_type=ProductImageVariantType.CARD.value,
        extension=".webp",
    )
    stored = await storage.save_product_variant(
        content=content,
        variant_type=ProductImageVariantType.CARD.value,
        extension="webp",
    )

    assert planned.url == f"https://cdn.mvn.by/media/products/variants/card/{content_hash}.webp"
    assert planned.path == f"products/variants/card/{content_hash}.webp"
    assert stored == planned
    assert fake_client.calls == [
        {
            "Bucket": "mvn-media",
            "Key": f"products/variants/card/{content_hash}.webp",
            "Body": content,
            "ContentType": "image/webp",
            "CacheControl": "public, max-age=31536000, immutable",
            "Metadata": {
                "sha256": content_hash,
                "variant_type": "card",
            },
        }
    ]


def test_storage_factory_keeps_local_as_default(monkeypatch):
    monkeypatch.setenv("PRODUCT_MEDIA_STORAGE_PROVIDER", "local")

    storage = get_product_media_storage()

    assert isinstance(storage, LocalProductMediaStorage)


@pytest.mark.asyncio
async def test_r2_factory_allows_dry_run_without_access_key_secrets(monkeypatch):
    monkeypatch.setenv("PRODUCT_MEDIA_S3_BUCKET", "mvn-media")
    monkeypatch.setenv(
        "PRODUCT_MEDIA_S3_ENDPOINT_URL",
        "https://example-account.r2.cloudflarestorage.com",
    )
    monkeypatch.setenv("PRODUCT_MEDIA_S3_PUBLIC_BASE_URL", "https://cdn.mvn.by/media")
    monkeypatch.delenv("PRODUCT_MEDIA_S3_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("PRODUCT_MEDIA_S3_SECRET_ACCESS_KEY", raising=False)

    storage = get_product_media_storage("r2", require_write=False)
    planned = storage.build_product_variant_object(
        content_hash="b" * 64,
        variant_type=ProductImageVariantType.FULL.value,
        extension="webp",
    )

    assert planned.storage_provider == "r2"
    assert planned.url == f"https://cdn.mvn.by/media/products/variants/full/{'b' * 64}.webp"
    with pytest.raises(ValueError, match="access key credentials"):
        await storage.save_product_variant(
            content=b"content",
            variant_type=ProductImageVariantType.FULL.value,
        )
