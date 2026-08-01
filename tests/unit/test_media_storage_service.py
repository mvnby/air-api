import hashlib
from pathlib import Path

import pytest

from services.media_storage_service import (
    LocalProductOriginalSourceStorage,
    LocalProductMediaStorage,
    S3CompatibleProductOriginalSourceStorage,
    S3CompatibleProductMediaStorage,
    get_product_original_source_storage,
    get_product_media_storage,
)
from services.general_media_storage_service import (
    LocalGeneralMediaStorage,
    S3CompatibleGeneralMediaStorage,
    get_general_media_storage,
)
from services.product_image_processing_contract import ProductImageVariantType


class FakeS3Client:
    def __init__(self):
        self.calls = []
        self.objects = {}

    def put_object(self, **kwargs):
        self.calls.append(kwargs)
        self.objects[kwargs["Key"]] = kwargs["Body"]

    def get_object(self, **kwargs):
        content = self.objects[kwargs["Key"]]

        class Body:
            def read(self):
                return content

        return {"Body": Body()}

    def delete_object(self, **kwargs):
        self.objects.pop(kwargs["Key"], None)


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


def test_local_storage_keeps_original_variants_on_shared_url_path(tmp_path: Path):
    storage = LocalProductMediaStorage(
        base_dir=tmp_path / "media/products/variants",
        original_base_dir=tmp_path / "media/products/shared",
    )
    content_hash = "c" * 64

    target = storage.build_product_variant_object(
        content_hash=content_hash,
        variant_type=ProductImageVariantType.ORIGINAL.value,
        extension="webp",
    )

    assert target.storage_provider == "local"
    assert target.url == f"/media/products/shared/{content_hash}.webp"
    assert target.path.endswith(f"media/products/shared/{content_hash}.webp")


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


@pytest.mark.asyncio
async def test_s3_storage_serves_yandex_feed_variant_as_jpeg():
    fake_client = FakeS3Client()
    storage = S3CompatibleProductMediaStorage(
        provider_name="r2",
        bucket="mvn-media",
        endpoint_url="https://example-account.r2.cloudflarestorage.com",
        public_base_url="https://cdn.mvn.by/media",
        client=fake_client,
    )

    stored = await storage.save_product_variant(
        content=b"jpeg-bytes",
        variant_type=ProductImageVariantType.YANDEX_FEED.value,
        extension="jpg",
    )

    assert stored.url.endswith(".jpg")
    assert "/yandex-feed/" in stored.url
    assert fake_client.calls[0]["ContentType"] == "image/jpeg"
    assert fake_client.calls[0]["CacheControl"] == (
        "public, max-age=31536000, immutable"
    )


@pytest.mark.asyncio
async def test_general_s3_storage_uses_namespace_and_variant_keys():
    fake_client = FakeS3Client()
    storage = S3CompatibleGeneralMediaStorage(
        provider_name="r2",
        bucket="mvn-media",
        endpoint_url="https://example-account.r2.cloudflarestorage.com",
        public_base_url="https://cdn.mvn.by/media",
        key_prefix="",
        cache_control="public, max-age=31536000, immutable",
        client=fake_client,
    )
    content = b"telegram-photo"
    content_hash = hashlib.sha256(content).hexdigest()

    stored = await storage.save_media(
        content=content,
        namespace="orders/121/telegram",
        variant_type="photo",
        extension="jpg",
        content_type="image/jpeg",
    )

    assert stored.storage_provider == "r2"
    assert stored.url == f"https://cdn.mvn.by/media/orders/121/telegram/photo/{content_hash}.jpg"
    assert stored.path == f"orders/121/telegram/photo/{content_hash}.jpg"
    assert stored.size_bytes == len(content)
    assert fake_client.calls == [
        {
            "Bucket": "mvn-media",
            "Key": f"orders/121/telegram/photo/{content_hash}.jpg",
            "Body": content,
            "ContentType": "image/jpeg",
            "CacheControl": "public, max-age=31536000, immutable",
            "Metadata": {
                "sha256": content_hash,
                "namespace": "orders/121/telegram",
                "variant_type": "photo",
            },
        }
    ]
    assert await storage.read_media(stored.path) == content
    await storage.delete_media(stored.path)
    assert stored.path not in fake_client.objects


@pytest.mark.asyncio
async def test_product_original_r2_storage_uses_shared_prefix():
    fake_client = FakeS3Client()
    storage = S3CompatibleProductOriginalSourceStorage(
        provider_name="r2",
        bucket="mvn-media",
        endpoint_url="https://example-account.r2.cloudflarestorage.com",
        public_base_url="https://cdn.mvn.by/media",
        key_prefix="products/shared",
        cache_control="public, max-age=31536000, immutable",
        client=fake_client,
    )
    content = b"original-webp"
    content_hash = hashlib.sha256(content).hexdigest()

    stored = await storage.save_product_original(content=content, extension=".webp")

    assert stored.storage_provider == "r2"
    assert stored.url == f"https://cdn.mvn.by/media/products/shared/{content_hash}.webp"
    assert stored.path == f"products/shared/{content_hash}.webp"
    assert fake_client.calls[0]["Key"] == f"products/shared/{content_hash}.webp"
    assert fake_client.calls[0]["ContentType"] == "image/webp"


def test_storage_factory_keeps_local_as_default(monkeypatch):
    monkeypatch.setenv("PRODUCT_MEDIA_STORAGE_PROVIDER", "local")

    storage = get_product_media_storage()

    assert isinstance(storage, LocalProductMediaStorage)


def test_general_storage_factory_keeps_local_as_default(monkeypatch):
    monkeypatch.delenv("MEDIA_STORAGE_PROVIDER", raising=False)

    storage = get_general_media_storage()

    assert isinstance(storage, LocalGeneralMediaStorage)


def test_original_source_storage_factory_keeps_local_shared_defaults(monkeypatch):
    monkeypatch.delenv("PRODUCT_MEDIA_ORIGINAL_SOURCE_PROVIDER", raising=False)

    storage = get_product_original_source_storage()

    assert isinstance(storage, LocalProductOriginalSourceStorage)


def test_original_source_storage_factory_supports_r2(monkeypatch):
    monkeypatch.setenv("PRODUCT_MEDIA_ORIGINAL_SOURCE_PROVIDER", "r2")
    monkeypatch.setenv("PRODUCT_MEDIA_S3_BUCKET", "mvn-media")
    monkeypatch.setenv(
        "PRODUCT_MEDIA_S3_ENDPOINT_URL",
        "https://example-account.r2.cloudflarestorage.com",
    )
    monkeypatch.setenv("PRODUCT_MEDIA_S3_PUBLIC_BASE_URL", "https://cdn.mvn.by/media")
    monkeypatch.setenv("PRODUCT_MEDIA_S3_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("PRODUCT_MEDIA_S3_SECRET_ACCESS_KEY", "secret")

    storage = get_product_original_source_storage()

    assert isinstance(storage, S3CompatibleProductOriginalSourceStorage)


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
