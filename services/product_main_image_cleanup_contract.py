"""Contracts for product main-image cleanup lifecycle."""

from __future__ import annotations

from enum import Enum


class ProductMainImageCleanupStatus(str, Enum):
    PENDING = "pending"
    SKIPPED = "skipped"
    PROCESSING = "processing"
    CANDIDATE_READY = "candidate_ready"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"


class ProductMainImageCleanupProcessor(str, Enum):
    MANUAL = "manual"
    NOOP = "noop"
    SAFE_BG_CLEANUP = "safe_bg_cleanup"


class ProductMainImageCleanupSkipReason(str, Enum):
    ALREADY_PROCESSED = "already_processed"
    ALREADY_TRANSPARENT = "already_transparent"
    MISSING_MAIN_IMAGE = "missing_main_image"
    MISSING_LOCAL_SOURCE = "missing_local_source"
    REMOTE_SOURCE_UNSUPPORTED = "remote_source_unsupported"


MAIN_IMAGE_CLEANUP_VARIANT_TYPE = "main_cleanup"
DEFAULT_MAIN_IMAGE_CLEANUP_PROCESSOR_VERSION = "main-cleanup-v1"


def normalize_cleanup_processor(value: str | ProductMainImageCleanupProcessor | None) -> str:
    if value is None:
        return ProductMainImageCleanupProcessor.NOOP.value
    if isinstance(value, ProductMainImageCleanupProcessor):
        return value.value
    try:
        return ProductMainImageCleanupProcessor(str(value)).value
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ProductMainImageCleanupProcessor)
        raise ValueError(f"Unsupported cleanup processor={value!r}. Allowed: {allowed}") from exc
