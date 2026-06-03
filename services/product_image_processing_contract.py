"""Contracts for product image variant processing.

The database stores these values as strings so migrations stay portable, while
services validate against these enums before writing status/stage data.
"""

from __future__ import annotations

from enum import Enum


class ProductImageVariantType(str, Enum):
    ORIGINAL = "original"
    PROCESSED = "processed"
    CARD = "card"
    FULL = "full"


class ProductImageProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    SKIPPED = "skipped"
    MANUAL_REVIEW = "manual_review"


class ProductImageProcessingStage(str, Enum):
    ORIGINAL_INGEST = "original_ingest"
    BACKGROUND_REMOVAL = "background_removal"
    TRANSPARENT_TRIM = "transparent_trim"
    CANVAS_NORMALIZATION = "canvas_normalization"
    CLASSIC_ENHANCEMENT = "classic_enhancement"
    VARIANT_GENERATION = "variant_generation"
    STORAGE_SAVE = "storage_save"
    QUALITY_MANUAL_APPROVAL = "quality_manual_approval"


class ProductImageManualQualityStatus(str, Enum):
    UNREVIEWED = "unreviewed"
    APPROVED = "approved"
    REJECTED = "rejected"


class ProductImageProcessingProvider(str, Enum):
    MANUAL = "manual"
    NOOP = "noop"
    REMBG = "rembg"


CATALOG_VARIANT_TYPES = {
    ProductImageVariantType.PROCESSED.value,
    ProductImageVariantType.CARD.value,
    ProductImageVariantType.FULL.value,
}


def normalize_variant_type(value: str | ProductImageVariantType) -> ProductImageVariantType:
    if isinstance(value, ProductImageVariantType):
        return value
    try:
        return ProductImageVariantType(str(value))
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ProductImageVariantType)
        raise ValueError(f"Unsupported image variant_type={value!r}. Allowed: {allowed}") from exc


def normalize_processing_provider(
    value: str | ProductImageProcessingProvider | None,
) -> ProductImageProcessingProvider:
    if value is None:
        return ProductImageProcessingProvider.NOOP
    if isinstance(value, ProductImageProcessingProvider):
        return value
    try:
        return ProductImageProcessingProvider(str(value))
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ProductImageProcessingProvider)
        raise ValueError(f"Unsupported image processing provider={value!r}. Allowed: {allowed}") from exc
