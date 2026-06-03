"""Storage contracts for product media variants."""

from __future__ import annotations

import asyncio
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class StoredMediaObject:
    url: str
    content_hash: str
    storage_provider: str
    path: str


class ProductMediaStorage(Protocol):
    provider_name: str

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

    async def save_product_variant(
        self,
        *,
        content: bytes,
        variant_type: str,
        extension: str = "webp",
    ) -> StoredMediaObject:
        if not content:
            raise ValueError("Cannot store empty media content")

        safe_extension = extension.lower().lstrip(".") or "webp"
        content_hash = hashlib.sha256(content).hexdigest()
        target_dir = self.base_dir / variant_type
        target_path = target_dir / f"{content_hash}.{safe_extension}"

        target_dir.mkdir(parents=True, exist_ok=True)
        if not target_path.exists():
            async with self._write_lock:
                if not target_path.exists():
                    target_path.write_bytes(content)

        relative_path = str(target_path).replace(os.sep, "/")
        public_url = f"{self.public_prefix}/{variant_type}/{target_path.name}"
        return StoredMediaObject(
            url=public_url,
            content_hash=content_hash,
            storage_provider=self.provider_name,
            path=relative_path,
        )


class S3CompatibleProductMediaStorage:
    """Future adapter shape for S3/R2-compatible storage.

    The first image-variant PR only ships local storage. This placeholder keeps
    the service contract explicit without introducing cloud credentials or SDK
    dependencies into production.
    """

    provider_name = "s3_compatible"

    async def save_product_variant(
        self,
        *,
        content: bytes,
        variant_type: str,
        extension: str = "webp",
    ) -> StoredMediaObject:
        raise NotImplementedError("S3/R2-compatible storage is reserved for a later stage")
