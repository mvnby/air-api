"""Provider adapter contract for product main-image cleanup candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from services.product_image_processing_provider import (
    ProductImageProcessingContext,
    ProductImageProcessingResult,
    _process_image_bytes,
)
from services.product_main_image_cleanup_contract import (
    DEFAULT_MAIN_IMAGE_CLEANUP_PROCESSOR_VERSION,
    MAIN_IMAGE_CLEANUP_VARIANT_TYPE,
    ProductMainImageCleanupProcessor,
    normalize_cleanup_processor,
)


@dataclass(frozen=True)
class ProductMainImageCleanupContext:
    product_id: int
    source_url: str
    source_product_image_id: int | None = None


@dataclass(frozen=True)
class ProductMainImageCleanupResult:
    content: bytes
    extension: str
    width: int | None
    height: int | None
    processor_method: str
    processor_version: str
    confidence_score: float | None = None
    quality_score: float | None = None


class ProductMainImageCleanupProcessorAdapter(Protocol):
    processor_method: str
    processor_version: str

    async def process(
        self,
        *,
        source_content: bytes,
        context: ProductMainImageCleanupContext,
    ) -> ProductMainImageCleanupResult:
        """Return candidate bytes without mutating product or source records."""


class NoopMainImageCleanupProcessor:
    """Safe first-slice adapter: normalize/export only, no background removal."""

    processor_method = ProductMainImageCleanupProcessor.NOOP.value
    processor_version = DEFAULT_MAIN_IMAGE_CLEANUP_PROCESSOR_VERSION

    async def process(
        self,
        *,
        source_content: bytes,
        context: ProductMainImageCleanupContext,
    ) -> ProductMainImageCleanupResult:
        processed: ProductImageProcessingResult = _process_image_bytes(
            source_content,
            context=ProductImageProcessingContext(
                product_image_id=context.source_product_image_id or 0,
                source_url=context.source_url,
                variant_type=MAIN_IMAGE_CLEANUP_VARIANT_TYPE,
            ),
        )
        return ProductMainImageCleanupResult(
            content=processed.content,
            extension=processed.extension,
            width=processed.width,
            height=processed.height,
            processor_method=self.processor_method,
            processor_version=self.processor_version,
            confidence_score=1.0,
            quality_score=_heuristic_quality_score(processed.width, processed.height),
        )


class ManualMainImageCleanupProcessor(NoopMainImageCleanupProcessor):
    """Placeholder adapter for manual/operator-provided candidate flows."""

    processor_method = ProductMainImageCleanupProcessor.MANUAL.value


def get_main_image_cleanup_processor(
    processor: str | None,
) -> ProductMainImageCleanupProcessorAdapter:
    normalized = normalize_cleanup_processor(processor)
    if normalized == ProductMainImageCleanupProcessor.NOOP.value:
        return NoopMainImageCleanupProcessor()
    if normalized == ProductMainImageCleanupProcessor.MANUAL.value:
        return ManualMainImageCleanupProcessor()
    raise ValueError(f"Unsupported cleanup processor={processor!r}")


def _heuristic_quality_score(width: int | None, height: int | None) -> float | None:
    if not width or not height:
        return None
    short_edge = min(width, height)
    if short_edge >= 900:
        return 0.9
    if short_edge >= 600:
        return 0.8
    if short_edge >= 300:
        return 0.65
    return 0.45
