import io
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import UploadFile
from pydantic import ValidationError

from core.config import Settings
from routers.manager_service_attachments import _read_upload_limited
from services.private_attachment_storage_service import (
    LocalPrivateAttachmentStorage,
    S3PrivateAttachmentStorage,
    VariantScopedPrivateAttachmentStorage,
)


class _Body:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def read(self) -> bytes:
        return self.content


class _MissingObject(Exception):
    response = {"Error": {"Code": "NoSuchKey"}}


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.modified_at: dict[str, datetime] = {}
        self.put_calls: list[dict] = []
        self.list_calls: list[dict] = []

    def put_object(self, **kwargs):
        self.put_calls.append(kwargs)
        self.objects[kwargs["Key"]] = kwargs["Body"]
        self.modified_at[kwargs["Key"]] = datetime.now(timezone.utc)

    def get_object(self, **kwargs):
        try:
            return {"Body": _Body(self.objects[kwargs["Key"]])}
        except KeyError as exc:
            raise _MissingObject from exc

    def head_object(self, **kwargs):
        if kwargs["Key"] not in self.objects:
            raise _MissingObject
        return {}

    def delete_object(self, **kwargs):
        self.objects.pop(kwargs["Key"], None)
        self.modified_at.pop(kwargs["Key"], None)

    def list_objects_v2(self, **kwargs):
        self.list_calls.append(kwargs)
        prefix = kwargs.get("Prefix", "")
        keys = sorted(key for key in self.objects if key.startswith(prefix))
        start_after = kwargs.get("StartAfter")
        if start_after:
            keys = [key for key in keys if key > start_after]
        page_keys = keys[: kwargs.get("MaxKeys", 1000)]
        return {
            "Contents": [
                {"Key": key, "LastModified": self.modified_at[key]}
                for key in page_keys
            ],
            "IsTruncated": len(keys) > len(page_keys),
        }

    def generate_presigned_url(self, *args, **kwargs):
        del args
        return f"https://private.invalid/{kwargs['Params']['Key']}"


@pytest.mark.asyncio
async def test_local_private_storage_dedupes_bytes_and_verifies_round_trip(tmp_path):
    storage = LocalPrivateAttachmentStorage(tmp_path)
    digest = "a" * 64

    first = await storage.save(
        content=b"first",
        content_hash=digest,
        extension="txt",
        content_type="text/plain",
        variant="original",
    )
    second = await storage.save(
        content=b"changed but same digest is rejected by caller",
        content_hash=digest,
        extension="txt",
        content_type="text/plain",
        variant="original",
    )

    assert first.storage_key == second.storage_key
    assert await storage.read(first.storage_key) == b"first"
    assert await storage.exists(first.storage_key)
    await storage.verify_writable()


@pytest.mark.asyncio
async def test_local_private_storage_lists_only_aged_scoped_variants(tmp_path):
    storage = LocalPrivateAttachmentStorage(tmp_path)
    scoped = await storage.save(
        content=b"scoped",
        content_hash="c" * 64,
        extension="png",
        content_type="image/png",
        variant="public-installation-keyhash-original",
    )
    await storage.save(
        content=b"ordinary",
        content_hash="d" * 64,
        extension="png",
        content_type="image/png",
        variant="original",
    )

    page = await storage.list_reconciliation_page(
        variant_prefixes=("public-installation-", "public-repair-"),
        older_than=datetime.now(timezone.utc) + timedelta(seconds=1),
        cursor=None,
        limit=10,
    )

    assert [item.storage_key for item in page.candidates] == [scoped.storage_key]
    assert page.examined == 2
    assert page.wrapped is True
    assert page.next_cursor is None


@pytest.mark.asyncio
async def test_local_private_storage_pages_by_examined_objects_without_overfetch(
    tmp_path,
):
    storage = LocalPrivateAttachmentStorage(tmp_path)
    stored = []
    for index in range(5):
        stored.append(
            await storage.save(
                content=f"content-{index}".encode(),
                content_hash=f"{index:064x}",
                extension="png",
                content_type="image/png",
                variant=(
                    f"public-repair-scope-{index}-original"
                    if index == 4
                    else "ordinary"
                ),
            )
        )

    first = await storage.list_reconciliation_page(
        variant_prefixes=("public-repair-",),
        older_than=datetime.now(timezone.utc) + timedelta(seconds=1),
        cursor=None,
        limit=2,
    )
    second = await storage.list_reconciliation_page(
        variant_prefixes=("public-repair-",),
        older_than=datetime.now(timezone.utc) + timedelta(seconds=1),
        cursor=first.next_cursor,
        limit=2,
    )
    third = await storage.list_reconciliation_page(
        variant_prefixes=("public-repair-",),
        older_than=datetime.now(timezone.utc) + timedelta(seconds=1),
        cursor=second.next_cursor,
        limit=2,
    )

    assert first.examined == second.examined == 2
    assert first.candidates == second.candidates == ()
    assert third.examined == 1
    assert [item.storage_key for item in third.candidates] == [
        stored[-1].storage_key
    ]
    assert third.wrapped is True
    assert third.next_cursor is None


@pytest.mark.asyncio
async def test_variant_scoped_storage_decorates_writes_and_delegates_reads(tmp_path):
    underlying = LocalPrivateAttachmentStorage(tmp_path)
    storage = VariantScopedPrivateAttachmentStorage(
        underlying,
        variant_scope="public-installation-keyhash-attempt",
    )

    stored = await storage.save(
        content=b"scoped-content",
        content_hash="e" * 64,
        extension="png",
        content_type="image/png",
        variant="original",
    )

    assert stored.storage_key.endswith(
        "/public-installation-keyhash-attempt-original.png"
    )
    assert await storage.read(stored.storage_key) == b"scoped-content"


@pytest.mark.asyncio
async def test_s3_private_storage_uses_private_cache_headers_and_preflight_cleanup():
    client = FakeS3Client()
    storage = S3PrivateAttachmentStorage(
        bucket="private-evidence",
        endpoint_url="https://r2.invalid",
        access_key_id="access",
        secret_access_key="secret",
        region="auto",
        key_prefix="service-attachments",
        client=client,
    )
    stored = await storage.save(
        content=b"evidence",
        content_hash="b" * 64,
        extension="pdf",
        content_type="application/pdf",
        variant="original",
    )

    assert await storage.exists(stored.storage_key)
    assert client.put_calls[0]["CacheControl"] == "private, no-store"
    assert client.put_calls[0]["Metadata"]["sha256"] == "b" * 64
    await storage.verify_writable()
    assert all("healthcheck" not in key for key in client.objects)


@pytest.mark.asyncio
async def test_s3_private_storage_lists_only_aged_scoped_variants():
    client = FakeS3Client()
    storage = S3PrivateAttachmentStorage(
        bucket="private-evidence",
        endpoint_url="https://r2.invalid",
        access_key_id="access",
        secret_access_key="secret",
        region="auto",
        key_prefix="service-attachments",
        client=client,
    )
    scoped = await storage.save(
        content=b"scoped",
        content_hash="c" * 64,
        extension="png",
        content_type="image/png",
        variant="public-installation-keyhash-attempt-original",
    )
    ordinary = await storage.save(
        content=b"ordinary",
        content_hash="d" * 64,
        extension="png",
        content_type="image/png",
        variant="original",
    )
    old = datetime.now(timezone.utc) - timedelta(days=2)
    client.modified_at[scoped.storage_key] = old
    client.modified_at[ordinary.storage_key] = old

    page = await storage.list_reconciliation_page(
        variant_prefixes=("public-installation-", "public-repair-"),
        older_than=datetime.now(timezone.utc) - timedelta(days=1),
        cursor=None,
        limit=10,
    )

    assert [item.storage_key for item in page.candidates] == [scoped.storage_key]
    assert page.examined == 2
    assert page.wrapped is True
    assert client.list_calls == [
        {
            "Bucket": "private-evidence",
            "Prefix": "service-attachments/",
            "MaxKeys": 10,
        }
    ]


@pytest.mark.asyncio
async def test_s3_private_storage_uses_one_bounded_request_per_page():
    client = FakeS3Client()
    storage = S3PrivateAttachmentStorage(
        bucket="private-evidence",
        endpoint_url="https://r2.invalid",
        access_key_id="access",
        secret_access_key="secret",
        region="auto",
        key_prefix="service-attachments",
        client=client,
    )
    old = datetime.now(timezone.utc) - timedelta(days=2)
    for index in range(5):
        key = f"service-attachments/{index:02d}/public-repair-{index}.png"
        client.objects[key] = f"content-{index}".encode()
        client.modified_at[key] = old

    first = await storage.list_reconciliation_page(
        variant_prefixes=("public-repair-",),
        older_than=datetime.now(timezone.utc) - timedelta(days=1),
        cursor=None,
        limit=2,
    )
    second = await storage.list_reconciliation_page(
        variant_prefixes=("public-repair-",),
        older_than=datetime.now(timezone.utc) - timedelta(days=1),
        cursor=first.next_cursor,
        limit=2,
    )

    assert first.examined == second.examined == 2
    assert len(first.candidates) == len(second.candidates) == 2
    assert first.wrapped is second.wrapped is False
    assert len(client.list_calls) == 2
    assert all(call["MaxKeys"] == 2 for call in client.list_calls)
    assert "StartAfter" not in client.list_calls[0]
    assert client.list_calls[1]["StartAfter"] == first.next_cursor


def test_production_settings_require_dedicated_private_storage():
    common = {
        "SECRET_KEY": "test",
        "ADMIN_USERNAME": "admin",
        "ADMIN_PASSWORD": "admin",
        "ENVIRONMENT": "production",
    }
    with pytest.raises(ValidationError, match="dedicated private bucket"):
        Settings(**common, SERVICE_ATTACHMENT_STORAGE_PROVIDER="local")

    configured = Settings(
        **common,
        SERVICE_ATTACHMENT_STORAGE_PROVIDER="r2",
        SERVICE_ATTACHMENT_S3_BUCKET="private-evidence",
        SERVICE_ATTACHMENT_S3_ENDPOINT_URL="https://r2.invalid",
        SERVICE_ATTACHMENT_S3_ACCESS_KEY_ID="access",
        SERVICE_ATTACHMENT_S3_SECRET_ACCESS_KEY="secret",
    )
    assert configured.SERVICE_ATTACHMENT_STORAGE_PROVIDER == "r2"


@pytest.mark.asyncio
async def test_manager_upload_reader_stops_at_configured_limit(monkeypatch):
    monkeypatch.setattr(
        "routers.manager_service_attachments.settings.SERVICE_ATTACHMENT_MAX_SIZE_BYTES",
        4,
    )
    accepted = UploadFile(filename="ok.txt", file=io.BytesIO(b"1234"))
    rejected = UploadFile(filename="too-large.txt", file=io.BytesIO(b"12345"))

    assert await _read_upload_limited(accepted) == b"1234"
    with pytest.raises(ValueError, match="size limit"):
        await _read_upload_limited(rejected)
