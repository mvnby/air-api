"""Provider adapter contract for product main-image cleanup candidates."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Protocol

from PIL import Image, ImageChops

from services.product_image_processing_provider import (
    CARD_CANVAS_SIZE,
    ProductImageProcessingContext,
    ProductImageProcessingResult,
    _export_image,
    _normalize_card_canvas,
    _open_source_image,
    _process_image_bytes,
    _trim_transparent_borders,
)
from services.product_main_image_cleanup_contract import (
    DEFAULT_MAIN_IMAGE_CLEANUP_PROCESSOR_VERSION,
    MAIN_IMAGE_CLEANUP_VARIANT_TYPE,
    ProductMainImageCleanupProcessor,
    normalize_cleanup_processor,
)


SAFE_BG_CLEANUP_PROCESSOR_VERSION = "safe-bg-cleanup-v1"
SAFE_BG_CLEANUP_MAX_SOURCE_BYTES = 24 * 1024 * 1024
SAFE_BG_CLEANUP_MAX_SOURCE_PIXELS = 16_000_000
SAFE_BG_CLEANUP_ANALYSIS_MAX_EDGE = 720
SAFE_BG_CLEANUP_MIN_EDGE_WHITE_RATIO = 0.58
SAFE_BG_CLEANUP_MIN_BACKGROUND_RATIO = 0.08
SAFE_BG_CLEANUP_MAX_BACKGROUND_RATIO = 0.9
SAFE_BG_CLEANUP_MIN_FOREGROUND_RATIO = 0.035
SAFE_BG_CLEANUP_MAX_FOREGROUND_RATIO = 0.94
NEAR_WHITE_MIN_CHANNEL = 235
NEAR_WHITE_MIN_AVERAGE = 242
NEAR_WHITE_MAX_CHANNEL_DELTA = 28


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


class SafeBackgroundCleanupProcessor:
    """Conservative Pillow-only cleanup for border-connected white backgrounds."""

    processor_method = ProductMainImageCleanupProcessor.SAFE_BG_CLEANUP.value
    processor_version = SAFE_BG_CLEANUP_PROCESSOR_VERSION

    async def process(
        self,
        *,
        source_content: bytes,
        context: ProductMainImageCleanupContext,
    ) -> ProductMainImageCleanupResult:
        cleanup = _safe_background_cleanup_image(source_content)
        canvas = _normalize_card_canvas(cleanup.image)
        content, extension = _export_image(canvas)
        return ProductMainImageCleanupResult(
            content=content,
            extension=extension,
            width=canvas.width,
            height=canvas.height,
            processor_method=self.processor_method,
            processor_version=self.processor_version,
            confidence_score=cleanup.confidence_score,
            quality_score=_cleanup_quality_score(canvas, cleanup.confidence_score),
        )


def get_main_image_cleanup_processor(
    processor: str | None,
) -> ProductMainImageCleanupProcessorAdapter:
    normalized = normalize_cleanup_processor(processor)
    if normalized == ProductMainImageCleanupProcessor.NOOP.value:
        return NoopMainImageCleanupProcessor()
    if normalized == ProductMainImageCleanupProcessor.MANUAL.value:
        return ManualMainImageCleanupProcessor()
    if normalized == ProductMainImageCleanupProcessor.SAFE_BG_CLEANUP.value:
        return SafeBackgroundCleanupProcessor()
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


@dataclass(frozen=True)
class _SafeBackgroundCleanupResult:
    image: Image.Image
    confidence_score: float


@dataclass(frozen=True)
class _BorderWhiteMask:
    mask: Image.Image
    edge_white_ratio: float
    background_ratio: float


def _safe_background_cleanup_image(source_content: bytes) -> _SafeBackgroundCleanupResult:
    if len(source_content) > SAFE_BG_CLEANUP_MAX_SOURCE_BYTES:
        raise ValueError("Source image is too large for safe main-image cleanup")

    source = _open_source_image(source_content)
    if source.width * source.height > SAFE_BG_CLEANUP_MAX_SOURCE_PIXELS:
        raise ValueError("Source image has too many pixels for safe main-image cleanup")

    transparent_trim_ratio = _transparent_trim_ratio(source)
    image = _trim_transparent_borders(source)
    border_mask = _build_border_connected_white_mask(image)
    if border_mask is None:
        return _SafeBackgroundCleanupResult(
            image=image,
            confidence_score=0.92 if transparent_trim_ratio >= 0.04 else 0.42,
        )

    foreground_bbox = _foreground_bbox_after_mask(image, border_mask.mask)
    if not _is_safe_white_cleanup_candidate(
        image=image,
        border_mask=border_mask,
        foreground_bbox=foreground_bbox,
    ):
        return _SafeBackgroundCleanupResult(
            image=image,
            confidence_score=_low_confidence_score(border_mask, transparent_trim_ratio),
        )

    cleaned = _apply_transparency_mask(image, border_mask.mask)
    cleaned = _trim_transparent_borders(cleaned)
    confidence = _white_cleanup_confidence_score(border_mask, transparent_trim_ratio)
    return _SafeBackgroundCleanupResult(
        image=cleaned,
        confidence_score=confidence,
    )


def _transparent_trim_ratio(image: Image.Image) -> float:
    if image.mode != "RGBA":
        return 0.0
    bbox = image.getchannel("A").getbbox()
    if not bbox:
        return 0.0
    full_area = image.width * image.height
    if full_area <= 0:
        return 0.0
    bbox_area = max(0, bbox[2] - bbox[0]) * max(0, bbox[3] - bbox[1])
    return max(0.0, min(1.0, 1.0 - (bbox_area / full_area)))


def _build_border_connected_white_mask(image: Image.Image) -> _BorderWhiteMask | None:
    if image.width <= 0 or image.height <= 0:
        return None

    analysis_image = image.convert("RGBA")
    scale = min(
        1.0,
        SAFE_BG_CLEANUP_ANALYSIS_MAX_EDGE / max(analysis_image.width, analysis_image.height),
    )
    if scale < 1.0:
        analysis_size = (
            max(1, int(round(analysis_image.width * scale))),
            max(1, int(round(analysis_image.height * scale))),
        )
        analysis_image = analysis_image.resize(analysis_size, Image.Resampling.BOX)

    candidate = _near_white_candidate_map(analysis_image)
    edge_white_ratio = _edge_candidate_ratio(candidate, analysis_image.size)
    if edge_white_ratio < SAFE_BG_CLEANUP_MIN_EDGE_WHITE_RATIO:
        return None

    connected = _connected_border_mask(candidate, analysis_image.size)
    connected_mask = Image.frombytes("L", analysis_image.size, bytes(connected))
    if connected_mask.size != image.size:
        connected_mask = connected_mask.resize(image.size, Image.Resampling.NEAREST)

    histogram = connected_mask.histogram()
    background_ratio = histogram[255] / max(1, image.width * image.height)
    if background_ratio <= 0:
        return None
    return _BorderWhiteMask(
        mask=connected_mask,
        edge_white_ratio=edge_white_ratio,
        background_ratio=background_ratio,
    )


def _near_white_candidate_map(image: Image.Image) -> bytearray:
    candidate = bytearray(image.width * image.height)
    raw = image.tobytes()
    for offset in range(0, len(raw), 4):
        index = offset // 4
        red = raw[offset]
        green = raw[offset + 1]
        blue = raw[offset + 2]
        alpha = raw[offset + 3]
        if alpha < 16:
            continue
        channel_min = min(red, green, blue)
        channel_max = max(red, green, blue)
        channel_average = (red + green + blue) / 3
        if (
            channel_min >= NEAR_WHITE_MIN_CHANNEL
            and channel_average >= NEAR_WHITE_MIN_AVERAGE
            and channel_max - channel_min <= NEAR_WHITE_MAX_CHANNEL_DELTA
        ):
            candidate[index] = 1
    return candidate


def _edge_candidate_ratio(candidate: bytearray, size: tuple[int, int]) -> float:
    width, height = size
    if width <= 0 or height <= 0:
        return 0.0

    edge_indices: list[int] = []
    edge_indices.extend(range(width))
    if height > 1:
        edge_indices.extend(range((height - 1) * width, height * width))
    for y in range(1, max(1, height - 1)):
        edge_indices.append(y * width)
        if width > 1:
            edge_indices.append(y * width + width - 1)

    if not edge_indices:
        return 0.0
    return sum(1 for index in edge_indices if candidate[index]) / len(edge_indices)


def _connected_border_mask(candidate: bytearray, size: tuple[int, int]) -> bytearray:
    width, height = size
    total = width * height
    output = bytearray(total)
    visited = bytearray(total)
    queue: deque[int] = deque()

    def enqueue(index: int) -> None:
        if candidate[index] and not visited[index]:
            visited[index] = 1
            queue.append(index)

    for x in range(width):
        enqueue(x)
        enqueue((height - 1) * width + x)
    for y in range(1, height - 1):
        enqueue(y * width)
        enqueue(y * width + width - 1)

    while queue:
        index = queue.popleft()
        output[index] = 255
        x = index % width
        if x > 0:
            enqueue(index - 1)
        if x + 1 < width:
            enqueue(index + 1)
        if index >= width:
            enqueue(index - width)
        if index + width < total:
            enqueue(index + width)

    return output


def _foreground_bbox_after_mask(
    image: Image.Image,
    background_mask: Image.Image,
) -> tuple[int, int, int, int] | None:
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    remaining_alpha = ImageChops.subtract(alpha, background_mask)
    return remaining_alpha.getbbox()


def _is_safe_white_cleanup_candidate(
    *,
    image: Image.Image,
    border_mask: _BorderWhiteMask,
    foreground_bbox: tuple[int, int, int, int] | None,
) -> bool:
    if foreground_bbox is None:
        return False
    if not (
        SAFE_BG_CLEANUP_MIN_BACKGROUND_RATIO
        <= border_mask.background_ratio
        <= SAFE_BG_CLEANUP_MAX_BACKGROUND_RATIO
    ):
        return False

    foreground_area = max(0, foreground_bbox[2] - foreground_bbox[0]) * max(
        0,
        foreground_bbox[3] - foreground_bbox[1],
    )
    foreground_ratio = foreground_area / max(1, image.width * image.height)
    if not (
        SAFE_BG_CLEANUP_MIN_FOREGROUND_RATIO
        <= foreground_ratio
        <= SAFE_BG_CLEANUP_MAX_FOREGROUND_RATIO
    ):
        return False

    width_ratio = max(0, foreground_bbox[2] - foreground_bbox[0]) / max(1, image.width)
    height_ratio = max(0, foreground_bbox[3] - foreground_bbox[1]) / max(1, image.height)
    return width_ratio >= 0.08 and height_ratio >= 0.08


def _apply_transparency_mask(image: Image.Image, background_mask: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    red, green, blue, alpha = rgba.split()
    cleaned_alpha = ImageChops.subtract(alpha, background_mask)
    return Image.merge("RGBA", (red, green, blue, cleaned_alpha))


def _low_confidence_score(
    border_mask: _BorderWhiteMask,
    transparent_trim_ratio: float,
) -> float:
    score = 0.46
    if border_mask.edge_white_ratio >= SAFE_BG_CLEANUP_MIN_EDGE_WHITE_RATIO:
        score += 0.08
    if border_mask.background_ratio >= SAFE_BG_CLEANUP_MIN_BACKGROUND_RATIO:
        score += 0.06
    if transparent_trim_ratio >= 0.04:
        score += 0.08
    return round(min(score, 0.72), 4)


def _white_cleanup_confidence_score(
    border_mask: _BorderWhiteMask,
    transparent_trim_ratio: float,
) -> float:
    edge_component = min(1.0, border_mask.edge_white_ratio) * 0.12
    coverage_component = min(1.0, border_mask.background_ratio / 0.45) * 0.08
    transparency_component = min(transparent_trim_ratio, 0.2) * 0.25
    score = 0.76 + edge_component + coverage_component + transparency_component
    return round(min(0.96, score), 4)


def _cleanup_quality_score(image: Image.Image, confidence_score: float) -> float | None:
    dimension_score = _heuristic_quality_score(image.width, image.height)
    if dimension_score is None:
        return None

    alpha_bbox = image.convert("RGBA").getchannel("A").getbbox()
    if not alpha_bbox:
        return 0.1

    width_ratio = max(0, alpha_bbox[2] - alpha_bbox[0]) / max(1, image.width)
    height_ratio = max(0, alpha_bbox[3] - alpha_bbox[1]) / max(1, image.height)
    longest_ratio = max(width_ratio, height_ratio)
    shortest_ratio = min(width_ratio, height_ratio)
    if longest_ratio < 0.35 or shortest_ratio < 0.18:
        occupancy_score = 0.52
    elif longest_ratio > 0.96:
        occupancy_score = 0.64
    elif longest_ratio > 0.88:
        occupancy_score = 0.78
    else:
        occupancy_score = 0.88

    score = (dimension_score * 0.4) + (occupancy_score * 0.35) + (confidence_score * 0.25)
    return round(max(0.1, min(0.98, score)), 4)
