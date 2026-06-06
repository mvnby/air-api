"""Shared ingest helpers for product original media."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from io import BytesIO

from PIL import Image

from services.media_storage_service import (
    ProductOriginalSourceStorage,
    StoredMediaObject,
    get_product_original_source_storage,
)


@dataclass(frozen=True)
class IngestedProductOriginal:
    url: str
    path: str
    content_hash: str
    content: bytes
    width: int | None
    height: int | None
    source_storage_provider: str


class ProductOriginalMediaService:
    @staticmethod
    async def save_shared_original(
        image_content: bytes,
        *,
        source_storage: ProductOriginalSourceStorage | None = None,
    ) -> IngestedProductOriginal:
        webp_content, width, height = await ProductOriginalMediaService.to_webp_bytes(
            image_content
        )
        storage = source_storage or get_product_original_source_storage()
        stored = await storage.save_product_original(
            content=webp_content,
            extension="webp",
        )
        return ProductOriginalMediaService._serialize_ingested(
            stored=stored,
            content=webp_content,
            width=width,
            height=height,
        )

    @staticmethod
    async def to_webp_bytes(content: bytes) -> tuple[bytes, int | None, int | None]:
        def process(payload: bytes) -> tuple[bytes, int | None, int | None]:
            with Image.open(BytesIO(payload)) as img:
                width, height = img.size
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                output = BytesIO()
                img.save(output, format="WEBP", quality=85)
                return output.getvalue(), width, height

        return await asyncio.to_thread(process, content)

    @staticmethod
    def _serialize_ingested(
        *,
        stored: StoredMediaObject,
        content: bytes,
        width: int | None,
        height: int | None,
    ) -> IngestedProductOriginal:
        return IngestedProductOriginal(
            url=stored.url,
            path=stored.path,
            content_hash=stored.content_hash,
            content=content,
            width=width,
            height=height,
            source_storage_provider=stored.storage_provider,
        )
