"""Private object storage for customer and field-service evidence."""

from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit


@dataclass(frozen=True)
class StoredPrivateObject:
    provider: str
    storage_key: str
    content_hash: str
    size_bytes: int


@dataclass(frozen=True)
class PrivateStorageCandidate:
    storage_key: str
    modified_at: datetime


@dataclass(frozen=True)
class PrivateStoragePage:
    candidates: tuple[PrivateStorageCandidate, ...]
    next_cursor: str | None
    examined: int
    wrapped: bool


class PrivateAttachmentStorage(Protocol):
    provider_name: str
    inventory_id: str

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

    async def exists(self, storage_key: str) -> bool: ...

    async def delete(self, storage_key: str) -> None: ...

    async def list_reconciliation_page(
        self,
        *,
        variant_prefixes: tuple[str, ...],
        older_than: datetime,
        cursor: str | None,
        limit: int,
    ) -> PrivateStoragePage: ...

    async def verify_writable(self) -> None: ...

    async def presign(self, storage_key: str, *, expires_seconds: int, download_name: str | None = None) -> str | None: ...


def _safe_extension(value: str) -> str:
    normalized = str(value or "bin").lower().lstrip(".")
    if not normalized or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789" for ch in normalized):
        return "bin"
    return "jpg" if normalized in {"jpeg", "jpe"} else normalized


def _safe_segment(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value or "")).strip("-")
    return normalized or "file"


def _validate_https_endpoint(endpoint_url: str) -> None:
    try:
        parsed_endpoint = urlsplit(endpoint_url)
        parsed_endpoint.port
    except ValueError:
        parsed_endpoint = None
    if (
        parsed_endpoint is None
        or parsed_endpoint.scheme.lower() != "https"
        or not parsed_endpoint.hostname
        or parsed_endpoint.username is not None
        or parsed_endpoint.password is not None
        or parsed_endpoint.query
        or parsed_endpoint.fragment
        or any(char.isspace() for char in endpoint_url)
    ):
        raise ValueError(
            "Private attachment S3 endpoint must be a credential-free HTTPS URL"
        )


def _deterministic_key(*, prefix: str, content_hash: str, variant: str, extension: str) -> str:
    digest = str(content_hash or "").strip().lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError("content_hash must be a SHA-256 digest")
    parts = [part for part in str(prefix or "").replace("\\", "/").split("/") if part]
    safe_prefix = [_safe_segment(part) for part in parts]
    return "/".join([*safe_prefix, digest[:2], digest[2:4], digest, f"{_safe_segment(variant)}.{_safe_extension(extension)}"])


class VariantScopedPrivateAttachmentStorage:
    """Prefix write variants while preserving the underlying storage identity."""

    def __init__(
        self,
        storage: PrivateAttachmentStorage,
        *,
        variant_scope: str,
    ) -> None:
        normalized_scope = _safe_segment(variant_scope)
        if normalized_scope != variant_scope or len(normalized_scope) > 128:
            raise ValueError("Invalid private attachment variant scope")
        self.storage = storage
        self.variant_scope = normalized_scope
        self.provider_name = storage.provider_name
        self.inventory_id = storage.inventory_id

    async def save(
        self,
        *,
        content: bytes,
        content_hash: str,
        extension: str,
        content_type: str,
        variant: str,
    ) -> StoredPrivateObject:
        return await self.storage.save(
            content=content,
            content_hash=content_hash,
            extension=extension,
            content_type=content_type,
            variant=f"{self.variant_scope}-{variant}",
        )

    async def read(self, storage_key: str) -> bytes:
        return await self.storage.read(storage_key)

    async def exists(self, storage_key: str) -> bool:
        return await self.storage.exists(storage_key)

    async def delete(self, storage_key: str) -> None:
        await self.storage.delete(storage_key)

    async def list_reconciliation_page(
        self,
        *,
        variant_prefixes: tuple[str, ...],
        older_than: datetime,
        cursor: str | None,
        limit: int,
    ) -> PrivateStoragePage:
        return await self.storage.list_reconciliation_page(
            variant_prefixes=variant_prefixes,
            older_than=older_than,
            cursor=cursor,
            limit=limit,
        )

    async def verify_writable(self) -> None:
        await self.storage.verify_writable()

    async def presign(
        self,
        storage_key: str,
        *,
        expires_seconds: int,
        download_name: str | None = None,
    ) -> str | None:
        return await self.storage.presign(
            storage_key,
            expires_seconds=expires_seconds,
            download_name=download_name,
        )


class LocalPrivateAttachmentStorage:
    provider_name = "local"

    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir).expanduser().resolve()
        self.inventory_id = hashlib.sha256(
            f"local:{self.base_dir}".encode("utf-8")
        ).hexdigest()
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

    async def exists(self, storage_key: str) -> bool:
        return await asyncio.to_thread(self._path(storage_key).is_file)

    async def delete(self, storage_key: str) -> None:
        path = self._path(storage_key)
        try:
            await asyncio.to_thread(path.unlink)
        except FileNotFoundError:
            pass

    async def list_reconciliation_page(
        self,
        *,
        variant_prefixes: tuple[str, ...],
        older_than: datetime,
        cursor: str | None,
        limit: int,
    ) -> PrivateStoragePage:
        cutoff = older_than.astimezone(timezone.utc)
        requested_limit = max(1, min(int(limit), 1000))
        normalized_cursor = str(cursor or "")[:1024] or None
        prefixes = tuple(str(prefix) for prefix in variant_prefixes if prefix)

        def iter_files_after(
            directory: Path,
            relative_prefix: str = "",
        ):
            try:
                entries = sorted(
                    os.scandir(directory),
                    key=lambda entry: entry.name,
                )
            except FileNotFoundError:
                return
            for entry in entries:
                relative_key = (
                    f"{relative_prefix}/{entry.name}"
                    if relative_prefix
                    else entry.name
                )
                if entry.is_dir(follow_symlinks=False):
                    subtree_prefix = f"{relative_key}/"
                    if (
                        normalized_cursor
                        and not normalized_cursor.startswith(subtree_prefix)
                        and subtree_prefix <= normalized_cursor
                    ):
                        continue
                    yield from iter_files_after(
                        Path(entry.path),
                        relative_key,
                    )
                elif entry.is_file(follow_symlinks=False) and (
                    normalized_cursor is None or relative_key > normalized_cursor
                ):
                    yield relative_key, entry

        def collect() -> PrivateStoragePage:
            candidates: list[PrivateStorageCandidate] = []
            examined = 0
            last_key: str | None = None
            for storage_key, entry in iter_files_after(self.base_dir):
                examined += 1
                last_key = storage_key
                filename = storage_key.rsplit("/", 1)[-1]
                if not filename.startswith(prefixes):
                    if examined >= requested_limit:
                        break
                    continue
                modified_at = datetime.fromtimestamp(
                    entry.stat(follow_symlinks=False).st_mtime,
                    tz=timezone.utc,
                )
                if modified_at <= cutoff:
                    candidates.append(
                        PrivateStorageCandidate(
                            storage_key=storage_key,
                            modified_at=modified_at,
                        )
                    )
                if examined >= requested_limit:
                    break
            wrapped = examined < requested_limit
            return PrivateStoragePage(
                candidates=tuple(candidates),
                next_cursor=None if wrapped else last_key,
                examined=examined,
                wrapped=wrapped,
            )

        return await asyncio.to_thread(collect)

    async def verify_writable(self) -> None:
        content = f"mvn-private-storage-{secrets.token_hex(16)}".encode()
        digest = hashlib.sha256(content).hexdigest()
        stored = await self.save(
            content=content,
            content_hash=digest,
            extension="txt",
            content_type="text/plain",
            variant="healthcheck",
        )
        try:
            if await self.read(stored.storage_key) != content:
                raise RuntimeError("Private local storage read-back mismatch")
        finally:
            await self.delete(stored.storage_key)
        if await self.exists(stored.storage_key):
            raise RuntimeError("Private local storage delete verification failed")

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
        inventory_material = (
            f"s3:{self.endpoint_url}:{self.bucket}:{self.key_prefix}"
        )
        self.inventory_id = hashlib.sha256(
            inventory_material.encode("utf-8")
        ).hexdigest()
        self._client_override = client
        self._client: Any | None = None
        missing = [
            name
            for name, value in (
                ("bucket", self.bucket),
                ("endpoint", self.endpoint_url),
                ("access key", self.access_key_id),
                ("secret key", self.secret_access_key),
            )
            if not value
        ]
        if missing:
            raise ValueError("Private attachment S3 storage requires " + ", ".join(missing))
        _validate_https_endpoint(self.endpoint_url)

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
            config=Config(
                signature_version="s3v4",
                connect_timeout=5,
                read_timeout=10,
                retries={"max_attempts": 2, "mode": "standard"},
                s3={"addressing_style": "path"},
            ),
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

    async def exists(self, storage_key: str) -> bool:
        try:
            await asyncio.to_thread(
                self._get_client().head_object,
                Bucket=self.bucket,
                Key=storage_key,
            )
        except Exception as exc:
            response = getattr(exc, "response", {}) or {}
            error = response.get("Error", {}) if isinstance(response, dict) else {}
            if str(error.get("Code") or "") in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise
        return True

    async def delete(self, storage_key: str) -> None:
        await asyncio.to_thread(
            self._get_client().delete_object,
            Bucket=self.bucket,
            Key=storage_key,
        )

    async def list_reconciliation_page(
        self,
        *,
        variant_prefixes: tuple[str, ...],
        older_than: datetime,
        cursor: str | None,
        limit: int,
    ) -> PrivateStoragePage:
        cutoff = older_than.astimezone(timezone.utc)
        requested_limit = max(1, min(int(limit), 1000))
        prefixes = tuple(str(prefix) for prefix in variant_prefixes if prefix)
        candidates: list[PrivateStorageCandidate] = []
        kwargs: dict[str, Any] = {
            "Bucket": self.bucket,
            "Prefix": f"{self.key_prefix}/" if self.key_prefix else "",
            "MaxKeys": requested_limit,
        }
        if cursor:
            kwargs["StartAfter"] = str(cursor)[:1024]
        response = await asyncio.to_thread(
            self._get_client().list_objects_v2,
            **kwargs,
        )
        raw_items = list(response.get("Contents") or [])
        examined_items = raw_items[:requested_limit]
        for item in examined_items:
            storage_key = str(item.get("Key") or "")
            filename = storage_key.rsplit("/", 1)[-1]
            modified_at = item.get("LastModified")
            if (
                storage_key
                and filename.startswith(prefixes)
                and isinstance(modified_at, datetime)
                and modified_at.astimezone(timezone.utc) <= cutoff
            ):
                candidates.append(
                    PrivateStorageCandidate(
                        storage_key=storage_key,
                        modified_at=modified_at.astimezone(timezone.utc),
                    )
                )
        has_more = bool(response.get("IsTruncated")) or len(raw_items) > requested_limit
        if has_more and not examined_items:
            raise RuntimeError("Private storage returned an empty truncated page")
        next_cursor = (
            str(examined_items[-1].get("Key") or "") or None
            if has_more
            else None
        )
        return PrivateStoragePage(
            candidates=tuple(candidates),
            next_cursor=next_cursor,
            examined=len(examined_items),
            wrapped=not has_more,
        )

    async def verify_writable(self) -> None:
        content = f"mvn-private-storage-{secrets.token_hex(16)}".encode()
        digest = hashlib.sha256(content).hexdigest()
        stored = await self.save(
            content=content,
            content_hash=digest,
            extension="txt",
            content_type="text/plain",
            variant="healthcheck",
        )
        try:
            if await self.read(stored.storage_key) != content:
                raise RuntimeError("Private S3 storage read-back mismatch")
        finally:
            await self.delete(stored.storage_key)
        if await self.exists(stored.storage_key):
            raise RuntimeError("Private S3 storage delete verification failed")

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


def _build_private_attachment_storage(
    current_settings: Any,
    provider: str | None = None,
    *,
    client: Any | None = None,
) -> PrivateAttachmentStorage:
    selected = (
        provider or current_settings.SERVICE_ATTACHMENT_STORAGE_PROVIDER or "local"
    ).strip().lower()
    if selected == "local":
        if current_settings.is_production:
            raise RuntimeError(
                "Production service attachments require a dedicated private R2/S3 bucket; "
                "local container storage is not persistent"
            )
        return LocalPrivateAttachmentStorage(
            current_settings.SERVICE_ATTACHMENT_LOCAL_DIR
        )
    if selected in {"r2", "s3", "s3_compatible"}:
        required = {
            "SERVICE_ATTACHMENT_S3_BUCKET": current_settings.SERVICE_ATTACHMENT_S3_BUCKET,
            "SERVICE_ATTACHMENT_S3_ENDPOINT_URL": current_settings.SERVICE_ATTACHMENT_S3_ENDPOINT_URL,
            "SERVICE_ATTACHMENT_S3_ACCESS_KEY_ID": current_settings.SERVICE_ATTACHMENT_S3_ACCESS_KEY_ID,
            "SERVICE_ATTACHMENT_S3_SECRET_ACCESS_KEY": current_settings.SERVICE_ATTACHMENT_S3_SECRET_ACCESS_KEY,
        }
        missing = [name for name, value in required.items() if not str(value or "").strip()]
        if missing:
            raise ValueError("Private attachment storage is missing: " + ", ".join(missing))
        return S3PrivateAttachmentStorage(
            bucket=current_settings.SERVICE_ATTACHMENT_S3_BUCKET,
            endpoint_url=current_settings.SERVICE_ATTACHMENT_S3_ENDPOINT_URL,
            access_key_id=current_settings.SERVICE_ATTACHMENT_S3_ACCESS_KEY_ID,
            secret_access_key=current_settings.SERVICE_ATTACHMENT_S3_SECRET_ACCESS_KEY,
            region=current_settings.SERVICE_ATTACHMENT_S3_REGION,
            key_prefix=current_settings.SERVICE_ATTACHMENT_S3_KEY_PREFIX,
            client=client,
        )
    raise ValueError(f"Unsupported SERVICE_ATTACHMENT_STORAGE_PROVIDER={selected!r}")


def get_private_attachment_storage(provider: str | None = None) -> PrivateAttachmentStorage:
    from core.config import settings

    return _build_private_attachment_storage(settings, provider)


async def verify_private_attachment_storage_startup(
    current_settings: Any,
    *,
    client: Any | None = None,
) -> None:
    if not current_settings.is_production:
        return

    provider = str(
        current_settings.SERVICE_ATTACHMENT_STORAGE_PROVIDER or ""
    ).strip().lower()
    if provider != "r2":
        raise RuntimeError("Production private attachment startup requires provider r2")

    private_bucket = str(current_settings.SERVICE_ATTACHMENT_S3_BUCKET or "").strip().casefold()
    public_buckets = {
        str(current_settings.MEDIA_S3_BUCKET or "").strip().casefold(),
        str(current_settings.PRODUCT_MEDIA_S3_BUCKET or "").strip().casefold(),
    }
    public_buckets.discard("")
    if private_bucket in public_buckets:
        raise RuntimeError(
            "Production private attachment bucket must be separate from public media buckets"
        )

    try:
        storage = _build_private_attachment_storage(
            current_settings,
            client=client,
        )
        await storage.verify_writable()
    except Exception as exc:
        raise RuntimeError(
            "Private attachment R2 startup probe failed "
            f"({type(exc).__name__}); check endpoint, credentials and bucket permissions"
        ) from None


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def extension_for(filename: str, mime_type: str | None) -> str:
    suffix = Path(filename or "").suffix.lstrip(".")
    if suffix:
        return _safe_extension(suffix)
    guessed = mimetypes.guess_extension((mime_type or "").split(";", 1)[0].strip())
    return _safe_extension(guessed or "bin")
