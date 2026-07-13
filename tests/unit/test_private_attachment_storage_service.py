import io

import pytest
from fastapi import UploadFile
from pydantic import ValidationError

from core.config import Settings
from routers.manager_service_attachments import _read_upload_limited
from services.private_attachment_storage_service import (
    LocalPrivateAttachmentStorage,
    S3PrivateAttachmentStorage,
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
        self.put_calls: list[dict] = []

    def put_object(self, **kwargs):
        self.put_calls.append(kwargs)
        self.objects[kwargs["Key"]] = kwargs["Body"]

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
