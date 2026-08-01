"""Storage adapters for non-product media files."""

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
class StoredGeneralMediaObject:
    url: str
    content_hash: str
    storage_provider: str
    path: str
    size_bytes: int


class GeneralMediaStorage(Protocol):
    provider_name: str

    def build_media_object(
        self,
        *,
        content_hash: str,
        namespace: str,
        variant_type: str,
        extension: str,
        size_bytes: int = 0,
    ) -> StoredGeneralMediaObject:
        """Return the deterministic storage target without writing content."""

    async def save_media(
        self,
        *,
        content: bytes,
        namespace: str,
        variant_type: str,
        extension: str,
        content_type: str | None = None,
    ) -> StoredGeneralMediaObject:
        """Persist media content and return its public URL plus metadata."""

    async def delete_media(self, path: str) -> None:
        """Delete a previously returned storage path."""


class LocalGeneralMediaStorage:
    provider_name = "local"

    def __init__(
        self,
        *,
        base_dir: str | Path = "media",
        public_prefix: str = "/media",
    ) -> None:
        self.base_dir = Path(base_dir)
        self.public_prefix = _normalize_public_prefix(public_prefix)
        self._write_lock = asyncio.Lock()

    def build_media_object(
        self,
        *,
        content_hash: str,
        namespace: str,
        variant_type: str,
        extension: str,
        size_bytes: int = 0,
    ) -> StoredGeneralMediaObject:
        safe_hash = _normalize_content_hash(content_hash)
        safe_extension = _normalize_extension(extension)
        key_parts = [*_safe_path_parts(namespace), _safe_path_segment(variant_type)]
        target_dir = self.base_dir.joinpath(*key_parts)
        target_path = target_dir / f"{safe_hash}.{safe_extension}"
        public_path = "/".join([*key_parts, target_path.name])
        return StoredGeneralMediaObject(
            url=_join_public_url(self.public_prefix, public_path),
            content_hash=safe_hash,
            storage_provider=self.provider_name,
            path=str(target_path).replace(os.sep, "/"),
            size_bytes=size_bytes,
        )

    async def save_media(
        self,
        *,
        content: bytes,
        namespace: str,
        variant_type: str,
        extension: str,
        content_type: str | None = None,
    ) -> StoredGeneralMediaObject:
        if not content:
            raise ValueError("Cannot store empty media content")

        content_hash = hashlib.sha256(content).hexdigest()
        stored = self.build_media_object(
            content_hash=content_hash,
            namespace=namespace,
            variant_type=variant_type,
            extension=extension,
            size_bytes=len(content),
        )
        target_path = Path(stored.path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if not target_path.exists():
            async with self._write_lock:
                if not target_path.exists():
                    target_path.write_bytes(content)
        return stored

    async def delete_media(self, path: str) -> None:
        target = Path(path).resolve()
        base = self.base_dir.resolve()
        if target != base and base not in target.parents:
            raise ValueError("Invalid general media storage path")
        if target.is_file():
            await asyncio.to_thread(target.unlink)


class S3CompatibleGeneralMediaStorage:
    """S3-compatible storage for shared media, including Cloudflare R2."""

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str,
        public_base_url: str,
        access_key_id: str = "",
        secret_access_key: str = "",
        region_name: str = "auto",
        key_prefix: str = "",
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
                "S3/R2 general media storage requires "
                + ", ".join(missing)
                + " configuration"
            )

    def build_media_object(
        self,
        *,
        content_hash: str,
        namespace: str,
        variant_type: str,
        extension: str,
        size_bytes: int = 0,
    ) -> StoredGeneralMediaObject:
        safe_hash = _normalize_content_hash(content_hash)
        safe_extension = _normalize_extension(extension)
        filename = f"{safe_hash}.{safe_extension}"
        key_parts = [
            *(_safe_path_parts(self.key_prefix) if self.key_prefix else []),
            *_safe_path_parts(namespace),
            _safe_path_segment(variant_type),
            filename,
        ]
        key = "/".join(key_parts)
        encoded_key = "/".join(quote(part, safe="") for part in key_parts)
        return StoredGeneralMediaObject(
            url=f"{self.public_base_url}/{encoded_key}",
            content_hash=safe_hash,
            storage_provider=self.provider_name,
            path=key,
            size_bytes=size_bytes,
        )

    async def save_media(
        self,
        *,
        content: bytes,
        namespace: str,
        variant_type: str,
        extension: str,
        content_type: str | None = None,
    ) -> StoredGeneralMediaObject:
        if not content:
            raise ValueError("Cannot store empty media content")

        stored = self.build_media_object(
            content_hash=hashlib.sha256(content).hexdigest(),
            namespace=namespace,
            variant_type=variant_type,
            extension=extension,
            size_bytes=len(content),
        )
        client = self._get_client()
        await asyncio.to_thread(
            client.put_object,
            Bucket=self.bucket,
            Key=stored.path,
            Body=content,
            ContentType=content_type or _content_type_for_extension(extension),
            CacheControl=self.cache_control,
            Metadata={
                "sha256": stored.content_hash,
                "namespace": "/".join(_safe_path_parts(namespace)),
                "variant_type": _safe_path_segment(variant_type),
            },
        )
        return stored

    async def delete_media(self, path: str) -> None:
        key = "/".join(_safe_path_parts(path))
        await asyncio.to_thread(
            self._get_client().delete_object,
            Bucket=self.bucket,
            Key=key,
        )

    def _get_client(self) -> Any:
        if self._client_override is not None:
            return self._client_override
        if self._client is not None:
            return self._client

        if not self.access_key_id or not self.secret_access_key:
            raise ValueError(
                "S3/R2 general media storage requires access key credentials for writes"
            )

        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise RuntimeError(
                "boto3 is required for S3/R2 general media storage. Install requirements first."
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


def get_general_media_storage(
    provider: str | None = None,
    *,
    require_write: bool = True,
) -> GeneralMediaStorage:
    load_dotenv()
    selected_provider = (provider or _env("MEDIA_STORAGE_PROVIDER", "local")).strip().lower()
    if selected_provider == "local":
        return LocalGeneralMediaStorage(
            base_dir=_env("MEDIA_LOCAL_DIR", "media"),
            public_prefix=_env("MEDIA_LOCAL_PUBLIC_PREFIX", "/media"),
        )

    if selected_provider in {"r2", "s3", "s3_compatible"}:
        access_key = _env_first(
            "MEDIA_S3_ACCESS_KEY_ID",
            "PRODUCT_MEDIA_S3_ACCESS_KEY_ID",
        ) if require_write else ""
        secret_key = _env_first(
            "MEDIA_S3_SECRET_ACCESS_KEY",
            "PRODUCT_MEDIA_S3_SECRET_ACCESS_KEY",
        ) if require_write else ""
        return S3CompatibleGeneralMediaStorage(
            provider_name=selected_provider,
            bucket=_env_first("MEDIA_S3_BUCKET", "PRODUCT_MEDIA_S3_BUCKET"),
            endpoint_url=_env_first("MEDIA_S3_ENDPOINT_URL", "PRODUCT_MEDIA_S3_ENDPOINT_URL"),
            public_base_url=_env_first(
                "MEDIA_S3_PUBLIC_BASE_URL",
                "PRODUCT_MEDIA_S3_PUBLIC_BASE_URL",
            ),
            access_key_id=access_key,
            secret_access_key=secret_key,
            region_name=_env_first("MEDIA_S3_REGION", "PRODUCT_MEDIA_S3_REGION", default="auto"),
            key_prefix=_env("MEDIA_S3_KEY_PREFIX", ""),
            cache_control=_env_first(
                "MEDIA_S3_CACHE_CONTROL",
                "PRODUCT_MEDIA_S3_CACHE_CONTROL",
                default="public, max-age=31536000, immutable",
            ),
        )

    raise ValueError(
        "Unsupported MEDIA_STORAGE_PROVIDER="
        f"{selected_provider!r}. Allowed: local, r2, s3, s3_compatible"
    )


def _normalize_extension(extension: str) -> str:
    safe_extension = (extension or "bin").lower().lstrip(".")
    if not safe_extension or "/" in safe_extension or "\\" in safe_extension:
        return "bin"
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


def _safe_path_parts(value: str) -> list[str]:
    return [
        _safe_path_segment(part)
        for part in str(value or "").replace("\\", "/").split("/")
        if part.strip()
    ]


def _normalize_key_prefix(value: str) -> str:
    return "/".join(_safe_path_parts(value))


def _normalize_public_prefix(value: str) -> str:
    normalized = str(value or "").strip().rstrip("/")
    if not normalized:
        return ""
    return normalized if normalized.startswith("/") else f"/{normalized}"


def _join_public_url(public_prefix: str, public_path: str) -> str:
    clean_path = public_path.strip("/")
    if public_prefix:
        return f"{public_prefix}/{clean_path}"
    return f"/{clean_path}"


def _content_type_for_extension(extension: str) -> str:
    guessed, _ = mimetypes.guess_type(f"file.{_normalize_extension(extension)}")
    return guessed or "application/octet-stream"


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _env_first(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return default
