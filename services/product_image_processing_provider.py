"""Provider contracts for product image processing."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Protocol

from PIL import Image

from services.product_image_processing_contract import ProductImageProcessingProvider


@dataclass(frozen=True)
class ProductImageProcessingContext:
    product_image_id: int
    source_url: str
    variant_type: str


@dataclass(frozen=True)
class ProductImageProcessingResult:
    content: bytes
    extension: str = "webp"
    width: int | None = None
    height: int | None = None


class ProductImageProcessor(Protocol):
    provider_name: str

    async def process(
        self,
        *,
        source_content: bytes,
        context: ProductImageProcessingContext,
    ) -> ProductImageProcessingResult:
        """Return processed image bytes ready for storage."""


class NoopProductImageProcessor:
    """Safe provider that stores the current bytes as the requested variant."""

    provider_name = ProductImageProcessingProvider.NOOP.value

    async def process(
        self,
        *,
        source_content: bytes,
        context: ProductImageProcessingContext,
    ) -> ProductImageProcessingResult:
        return ProductImageProcessingResult(content=source_content, extension="webp")


class ManualProductImageProcessor(NoopProductImageProcessor):
    """Alias for operator-approved manual processing flows."""

    provider_name = ProductImageProcessingProvider.MANUAL.value


class RembgProductImageProcessor:
    """Optional future provider; imports rembg lazily when explicitly selected."""

    provider_name = ProductImageProcessingProvider.REMBG.value

    async def process(
        self,
        *,
        source_content: bytes,
        context: ProductImageProcessingContext,
    ) -> ProductImageProcessingResult:
        try:
            from rembg import remove  # type: ignore
        except ImportError as exc:
            raise RuntimeError("rembg provider is not installed") from exc

        output = remove(source_content)
        image = Image.open(BytesIO(output))
        buffer = BytesIO()
        image.save(buffer, format="WEBP", quality=90)
        return ProductImageProcessingResult(content=buffer.getvalue(), extension="webp")


def get_product_image_processor(provider: str) -> ProductImageProcessor:
    if provider == ProductImageProcessingProvider.NOOP.value:
        return NoopProductImageProcessor()
    if provider == ProductImageProcessingProvider.MANUAL.value:
        return ManualProductImageProcessor()
    if provider == ProductImageProcessingProvider.REMBG.value:
        return RembgProductImageProcessor()
    raise ValueError(f"Unsupported image processing provider={provider!r}")
