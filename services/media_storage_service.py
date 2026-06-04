"""Storage contracts for product media variants."""

from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

from dotenv import load_dotenv


@dataclass(frozen=True)
class StoredMediaObject:
    url: str
    content_hash: str
    storage_provider: str
    path: str


class ProductMediaStorage(Protocol):
    provider_name: str

    def build_product_variant_object(
        self,
        *,
        content_hash: str,
        variant_type: str,
        extension: str = "webp",
    ) -> StoredMediaObject:
        """Return the deterministic storage target without writing content."""

    async def save_product_variant(
        self,
        *,
        content: bytes,
        variant_type: str,
        extension: str = "webp",
    ) -> StoredMediaObject:
        """Persist a variant and return a DB-safe URL plus provider metadata."""


class LocalProductMediaStorage:
    provider_name = "local"

    def __init__(
        self,
        base_dir: str | Path = "media/products/variants",
        public_prefix: str = "/media/products/variants",
    ) -> None:
        self.base_dir = Path(base_dir)
        self.public_prefix = public_prefix.rstrip("/") or "/media/products/variants"
        self._write_lock = asyncio.Lock()

    def build_product_variant_object(
        self,
        *,
        content_hash: str,
        variant_type: str,
        extension: str = "webp",
    ) -> StoredMediaObject:
        safe_extension = _normalize_extension(extension)
        safe_variant_type = _safe_path_segment(variant_type)
        safe_hash = _normalize_content_hash(content_hash)
        target_path = self.base_dir / safe_variant_type / f"{safe_hash}.{safe_extension}"
        relative_path = str(target_path).replace(os.sep, "/")
        public_url = f"{self.public_prefix}/{safe_variant_type}/{target_path.name}"
        return StoredMediaObject(
            url=public_url,
            content_hash=safe_hash,
            storage_provider=self.provider_name,
            path=relative_path,
        )

    async def save_product_variant(
        self,
        *,
        content: bytes,
        variant_type: str,
        extension: str = "webp",
    ) -> StoredMediaObject:
        if not content:
            raise ValueError("Cannot store empty media content")

        content_hash = hashlib.sha256(content).hexdigest()
        stored = self.build_product_variant_object(
            content_hash=content_hash,
            variant_type=variant_type,
            extension=extension,
        )
        target_path = Path(stored.path)

        target_path.parent.mkdir(parents=True, exist_ok=True)
        if not target_path.exists():
            async with self._write_lock:
                if not target_path.exists():
                    target_path.write_bytes(content)

        return stored


class S3CompatibleProductMediaStorage:
    """S3-compatible product media storage, including Cloudflare R2.

    URLs are intentionally public CDN URLs rather than signed proxy URLs. Object
    keys are content-addressed, so regenerated variants get new URLs and can use
    long immutable cache headers safely.
    """

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str,
        public_base_url: str,
        access_key_id: str = "",
        secret_access_key: str = "",
        region_name: str = "auto",
        key_prefix: str = "products/variants",
        cache_control: str = "public, max-age=31536000, immutable",
        provider_name: str = "s3_compatible",
        client: Any | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.bucket = bucket.strip()
        self.endpoint_url = endpoint_url.strip()
        self.public_base_url = public_base_url.strip().rstrip("/")
        self.access_key_id = access_key_id.strip()
        self.secret_access_key = secret_access_key.strip()
        self.region_name = region_name.strip() or "auto"
        self.key_prefix = _normalize_key_prefix(key_prefix)
        self.cache_control = cache_control.strip() or "public, max-age=31536000, immutable"
        self._client_override = client
        self._client: Any | None = None

        missing = [
            name
            for name, value in (
                ("bucket", self.bucket),
                ("endpoint_url", self.endpoint_url),
                ("public_base_url", self.public_base_url),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "S3/R2 media storage requires "
                + ", ".join(missing)
                + " configuration"
            )

    def build_product_variant_object(
        self,
        *,
        content_hash: str,
        variant_type: str,
        extension: str = "webp",
    ) -> StoredMediaObject:
        safe_extension = _normalize_extension(extension)
        safe_variant_type = _safe_path_segment(variant_type)
        safe_hash = _normalize_content_hash(content_hash)
        filename = f"{safe_hash}.{safe_extension}"
        key_parts = [part for part in (self.key_prefix, safe_variant_type, filename) if part]
        key = "/".join(key_parts)
        encoded_key = "/".join(quote(part, safe="") for part in key.split("/"))
        return StoredMediaObject(
            url=f"{self.public_base_url}/{encoded_key}",
            content_hash=safe_hash,
            storage_provider=self.provider_name,
            path=key,
        )

    async def save_product_variant(
        self,
        *,
        content: bytes,
        variant_type: str,
        extension: str = "webp",
    ) -> StoredMediaObject:
        if not content:
            raise ValueError("Cannot store empty media content")

        content_hash = hashlib.sha256(content).hexdigest()
        stored = self.build_product_variant_object(
            content_hash=content_hash,
            variant_type=variant_type,
            extension=extension,
        )
        client = self._get_client()
        await asyncio.to_thread(
            client.put_object,
            Bucket=self.bucket,
            Key=stored.path,
            Body=content,
            ContentType=_content_type_for_extension(extension),
            CacheControl=self.cache_control,
            Metadata={
                "sha256": stored.content_hash,
                "variant_type": _safe_path_segment(variant_type),
            },
        )
        return stored

    def _get_client(self) -> Any:
        if self._client_override is not None:
            return self._client_override
        if self._client is not None:
            return self._client

        if not self.access_key_id or not self.secret_access_key:
            raise ValueError(
                "S3/R2 media storage requires access key credentials for writes"
            )

        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise RuntimeError(
                "boto3 is required for S3/R2 media storage. Install requirements first."
            ) from exc

        self._client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            region_name=self.region_name,
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
        )
        return self._client


def get_product_media_storage(
    provider: str | None = None,
    *,
    require_write: bool = True,
) -> ProductMediaStorage:
    """Build the configured media storage adapter.

    `require_write=False` is intended for dry-run planning where public target
    URLs are needed but secret access keys should not be required.
    """
    load_dotenv()
    selected_provider = (provider or _env("PRODUCT_MEDIA_STORAGE_PROVIDER", "local")).strip().lower()
    if selected_provider == "local":
        return LocalProductMediaStorage(
            base_dir=_env("PRODUCT_MEDIA_LOCAL_VARIANT_DIR", "media/products/variants"),
            public_prefix=_env(
                "PRODUCT_MEDIA_LOCAL_VARIANT_PUBLIC_PREFIX",
                "/media/products/variants",
            ),
        )

    if selected_provider in {"r2", "s3", "s3_compatible"}:
        access_key = _env("PRODUCT_MEDIA_S3_ACCESS_KEY_ID") if require_write else ""
        secret_key = _env("PRODUCT_MEDIA_S3_SECRET_ACCESS_KEY") if require_write else ""
        return S3CompatibleProductMediaStorage(
            provider_name=selected_provider,
            bucket=_env("PRODUCT_MEDIA_S3_BUCKET"),
            endpoint_url=_env("PRODUCT_MEDIA_S3_ENDPOINT_URL"),
            public_base_url=_env("PRODUCT_MEDIA_S3_PUBLIC_BASE_URL"),
            access_key_id=access_key,
            secret_access_key=secret_key,
            region_name=_env("PRODUCT_MEDIA_S3_REGION", "auto"),
            key_prefix=_env("PRODUCT_MEDIA_S3_KEY_PREFIX", "products/variants"),
            cache_control=_env(
                "PRODUCT_MEDIA_S3_CACHE_CONTROL",
                "public, max-age=31536000, immutable",
            ),
        )

    raise ValueError(
        "Unsupported PRODUCT_MEDIA_STORAGE_PROVIDER="
        f"{selected_provider!r}. Allowed: local, r2, s3, s3_compatible"
    )


def _normalize_extension(extension: str) -> str:
    safe_extension = (extension or "webp").lower().lstrip(".")
    if not safe_extension or "/" in safe_extension or "\\" in safe_extension:
        return "webp"
    return safe_extension


def _normalize_content_hash(content_hash: str) -> str:
    value = (content_hash or "").strip().lower()
    if not value:
        raise ValueError("content_hash is required")
    if any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError("content_hash must be hexadecimal")
    return value


def _safe_path_segment(value: str) -> str:
    safe = "".join(
        ch.lower() if ch.isalnum() else "-"
        for ch in str(value or "").strip()
        if ch.isalnum() or ch in {"-", "_"}
    ).strip("-_")
    return safe or "default"


def _normalize_key_prefix(value: str) -> str:
    parts = [
        _safe_path_segment(part)
        for part in str(value or "").replace("\\", "/").split("/")
        if part.strip()
    ]
    return "/".join(parts)


def _content_type_for_extension(extension: str) -> str:
    safe_extension = _normalize_extension(extension)
    if safe_extension == "webp":
        return "image/webp"
    guessed, _ = mimetypes.guess_type(f"file.{safe_extension}")
    return guessed or "application/octet-stream"


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)
