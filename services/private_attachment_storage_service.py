"""Private object storage for customer and field-service evidence."""

from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from core.config import settings


@dataclass(frozen=True)
class StoredPrivateObject:
    provider: str
    storage_key: str
    content_hash: str
    size_bytes: int


class PrivateAttachmentStorage(Protocol):
    provider_name: str

    async def save(
        self,
        *,
        content: bytes,
        content_hash: str,
        extension: str,
        content_type: str,
        variant: str,
    ) -> StoredPrivateObject: ...

    async def read(self, storage_key: str) -> bytes: ...

    async def presign(self, storage_key: str, *, expires_seconds: int, download_name: str | None = None) -> str | None: ...


def _safe_extension(value: str) -> str:
    normalized = str(value or "bin").lower().lstrip(".")
    if not normalized or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789" for ch in normalized):
        return "bin"
    return "jpg" if normalized in {"jpeg", "jpe"} else normalized


def _safe_segment(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value or "")).strip("-")
    return normalized or "file"


def _deterministic_key(*, prefix: str, content_hash: str, variant: str, extension: str) -> str:
    digest = str(content_hash or "").strip().lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError("content_hash must be a SHA-256 digest")
    parts = [part for part in str(prefix or "").replace("\\", "/").split("/") if part]
    safe_prefix = [_safe_segment(part) for part in parts]
    return "/".join([*safe_prefix, digest[:2], digest[2:4], digest, f"{_safe_segment(variant)}.{_safe_extension(extension)}"])


class LocalPrivateAttachmentStorage:
    provider_name = "local"

    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir).expanduser().resolve()
        self._write_lock = asyncio.Lock()

    def _path(self, storage_key: str) -> Path:
        path = (self.base_dir / storage_key).resolve()
        if path != self.base_dir and self.base_dir not in path.parents:
            raise ValueError("Invalid private storage key")
        return path

    async def save(
        self,
        *,
        content: bytes,
        content_hash: str,
        extension: str,
        content_type: str,
        variant: str,
    ) -> StoredPrivateObject:
        del content_type
        if not content:
            raise ValueError("Cannot store an empty attachment")
        key = _deterministic_key(
            prefix="",
            content_hash=content_hash,
            variant=variant,
            extension=extension,
        )
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            async with self._write_lock:
                if not path.exists():
                    await asyncio.to_thread(path.write_bytes, content)
        return StoredPrivateObject(self.provider_name, key, content_hash, len(content))

    async def read(self, storage_key: str) -> bytes:
        path = self._path(storage_key)
        if not path.is_file():
            raise FileNotFoundError(storage_key)
        return await asyncio.to_thread(path.read_bytes)

    async def presign(self, storage_key: str, *, expires_seconds: int, download_name: str | None = None) -> str | None:
        del storage_key, expires_seconds, download_name
        return None


class S3PrivateAttachmentStorage:
    provider_name = "s3_compatible"

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str,
        access_key_id: str,
        secret_access_key: str,
        region: str,
        key_prefix: str,
        client: Any | None = None,
    ) -> None:
        self.bucket = bucket.strip()
        self.endpoint_url = endpoint_url.strip()
        self.access_key_id = access_key_id.strip()
        self.secret_access_key = secret_access_key.strip()
        self.region = region.strip() or "auto"
        self.key_prefix = key_prefix.strip(" /")
        self._client_override = client
        self._client: Any | None = None
        missing = [name for name, value in (("bucket", self.bucket), ("endpoint", self.endpoint_url)) if not value]
        if missing:
            raise ValueError("Private attachment S3 storage requires " + ", ".join(missing))

    def _get_client(self) -> Any:
        if self._client_override is not None:
            return self._client_override
        if self._client is not None:
            return self._client
        if not self.access_key_id or not self.secret_access_key:
            raise ValueError("Private attachment S3 storage requires write credentials")
        import boto3
        from botocore.config import Config

        self._client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            region_name=self.region,
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        return self._client

    async def save(
        self,
        *,
        content: bytes,
        content_hash: str,
        extension: str,
        content_type: str,
        variant: str,
    ) -> StoredPrivateObject:
        if not content:
            raise ValueError("Cannot store an empty attachment")
        key = _deterministic_key(
            prefix=self.key_prefix,
            content_hash=content_hash,
            variant=variant,
            extension=extension,
        )
        client = self._get_client()
        await asyncio.to_thread(
            client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType=content_type or mimetypes.guess_type(f"file.{extension}")[0] or "application/octet-stream",
            CacheControl="private, no-store",
            Metadata={"sha256": content_hash, "variant": variant},
        )
        return StoredPrivateObject(self.provider_name, key, content_hash, len(content))

    async def read(self, storage_key: str) -> bytes:
        response = await asyncio.to_thread(self._get_client().get_object, Bucket=self.bucket, Key=storage_key)
        return await asyncio.to_thread(response["Body"].read)

    async def presign(self, storage_key: str, *, expires_seconds: int, download_name: str | None = None) -> str | None:
        params: dict[str, Any] = {"Bucket": self.bucket, "Key": storage_key}
        if download_name:
            params["ResponseContentDisposition"] = f'attachment; filename="{download_name}"'
        return await asyncio.to_thread(
            self._get_client().generate_presigned_url,
            "get_object",
            Params=params,
            ExpiresIn=max(30, min(int(expires_seconds), 3600)),
        )


def get_private_attachment_storage(provider: str | None = None) -> PrivateAttachmentStorage:
    selected = (provider or settings.SERVICE_ATTACHMENT_STORAGE_PROVIDER or "local").strip().lower()
    if selected == "local":
        return LocalPrivateAttachmentStorage(settings.SERVICE_ATTACHMENT_LOCAL_DIR)
    if selected in {"r2", "s3", "s3_compatible"}:
        bucket = settings.SERVICE_ATTACHMENT_S3_BUCKET.strip()
        if not bucket:
            raise ValueError("SERVICE_ATTACHMENT_S3_BUCKET must point to a dedicated private bucket")
        return S3PrivateAttachmentStorage(
            bucket=bucket,
            endpoint_url=settings.SERVICE_ATTACHMENT_S3_ENDPOINT_URL or settings.MEDIA_S3_ENDPOINT_URL,
            access_key_id=settings.SERVICE_ATTACHMENT_S3_ACCESS_KEY_ID or settings.MEDIA_S3_ACCESS_KEY_ID,
            secret_access_key=settings.SERVICE_ATTACHMENT_S3_SECRET_ACCESS_KEY or settings.MEDIA_S3_SECRET_ACCESS_KEY,
            region=settings.SERVICE_ATTACHMENT_S3_REGION or settings.MEDIA_S3_REGION,
            key_prefix=settings.SERVICE_ATTACHMENT_S3_KEY_PREFIX,
        )
    raise ValueError(f"Unsupported SERVICE_ATTACHMENT_STORAGE_PROVIDER={selected!r}")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def extension_for(filename: str, mime_type: str | None) -> str:
    suffix = Path(filename or "").suffix.lstrip(".")
    if suffix:
        return _safe_extension(suffix)
    guessed = mimetypes.guess_extension((mime_type or "").split(";", 1)[0].strip())
    return _safe_extension(guessed or "bin")
