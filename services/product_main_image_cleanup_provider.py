"""Provider adapter contract for product main-image cleanup candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from PIL import Image, ImageChops, ImageFilter

from services.product_image_processing_provider import (
    PROCESSED_MAX_EDGE,
    ProductImageProcessingContext,
    ProductImageProcessingResult,
    _export_image,
    _open_source_image,
    _process_image_bytes,
    _resize_to_max_edge,
)
from services.product_main_image_cleanup_contract import (
    DEFAULT_MAIN_IMAGE_CLEANUP_PROCESSOR_VERSION,
    MAIN_IMAGE_CLEANUP_VARIANT_TYPE,
    ProductMainImageCleanupProcessor,
    normalize_cleanup_processor,
)


CLASSICAL_MAIN_IMAGE_CLEANUP_PROCESSOR_VERSION = "main-cleanup-classical-trim-v1"
WHITE_DELTA_THRESHOLD = 18
EDGE_DELTA_THRESHOLD = 20
ALPHA_CONTENT_THRESHOLD = 16
MIN_CROP_REDUCTION_RATIO = 0.08
MAX_TINY_OBJECT_CROP_REDUCTION_RATIO = 0.92
MIN_OBJECT_AREA_RATIO_FOR_AGGRESSIVE_CROP = 0.02
PADDING_RATIO = 0.10
MIN_PADDING_RATIO = 0.04
MAX_PADDING_RATIO = 0.18
EXPECTED_MIN_ASPECT_RATIO = 0.25
EXPECTED_MAX_ASPECT_RATIO = 4.0


ImageBox = tuple[int, int, int, int]


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


class ClassicalTrimMainImageCleanupProcessor:
    """Trim safe transparent/white margins and keep manual approval in front."""

    processor_method = ProductMainImageCleanupProcessor.CLASSICAL_TRIM.value
    processor_version = CLASSICAL_MAIN_IMAGE_CLEANUP_PROCESSOR_VERSION

    async def process(
        self,
        *,
        source_content: bytes,
        context: ProductMainImageCleanupContext,
    ) -> ProductMainImageCleanupResult:
        image = _open_source_image(source_content)
        detected_box = _detect_content_box(image)
        crop_box = _safe_crop_box(image, detected_box)
        cropped = image.crop(crop_box) if crop_box != _full_box(image) else image.copy()
        resized = _resize_to_max_edge(cropped, PROCESSED_MAX_EDGE)
        content, extension = _export_image(resized)
        scores = _score_classical_result(
            original_size=image.size,
            detected_box=detected_box,
            crop_box=crop_box,
            output_size=resized.size,
        )
        return ProductMainImageCleanupResult(
            content=content,
            extension=extension,
            width=resized.width,
            height=resized.height,
            processor_method=self.processor_method,
            processor_version=self.processor_version,
            confidence_score=scores.confidence_score,
            quality_score=scores.quality_score,
        )


def get_main_image_cleanup_processor(
    processor: str | None,
) -> ProductMainImageCleanupProcessorAdapter:
    normalized = normalize_cleanup_processor(processor)
    if normalized == ProductMainImageCleanupProcessor.CLASSICAL_TRIM.value:
        return ClassicalTrimMainImageCleanupProcessor()
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


@dataclass(frozen=True)
class _CleanupScores:
    confidence_score: float
    quality_score: float


def _detect_content_box(image: Image.Image) -> ImageBox | None:
    boxes: list[ImageBox] = []
    source_area = _image_area(image.size)

    alpha_mask = _alpha_mask(image)
    if alpha_mask is not None:
        alpha_box = alpha_mask.getbbox()
        if alpha_box and _box_area(alpha_box) / source_area < 0.98:
            boxes.append(alpha_box)

    foreground_mask = _near_white_foreground_mask(image)
    if alpha_mask is not None:
        foreground_mask = ImageChops.multiply(foreground_mask, alpha_mask)
    foreground_box = foreground_mask.getbbox()
    if foreground_box and _box_area(foreground_box) / source_area < 0.98:
        boxes.append(foreground_box)

    edge_mask = _edge_foreground_mask(image)
    if alpha_mask is not None:
        edge_mask = ImageChops.multiply(edge_mask, alpha_mask)
    edge_box = edge_mask.getbbox()
    if edge_box and _box_area(edge_box) / source_area < 0.98:
        boxes.append(edge_box)

    if not boxes:
        return None
    return _union_boxes(boxes)


def _safe_crop_box(image: Image.Image, detected_box: ImageBox | None) -> ImageBox:
    full_box = _full_box(image)
    if detected_box is None:
        return full_box

    source_area = _image_area(image.size)
    object_area_ratio = _box_area(detected_box) / source_area
    content_width = detected_box[2] - detected_box[0]
    content_height = detected_box[3] - detected_box[1]
    if content_width <= 0 or content_height <= 0:
        return full_box

    padding = _padding_for_box(image, detected_box)
    crop_box = (
        max(0, detected_box[0] - padding),
        max(0, detected_box[1] - padding),
        min(image.width, detected_box[2] + padding),
        min(image.height, detected_box[3] + padding),
    )
    crop_reduction_ratio = 1.0 - (_box_area(crop_box) / source_area)
    if crop_reduction_ratio < MIN_CROP_REDUCTION_RATIO:
        return full_box
    if (
        crop_reduction_ratio > MAX_TINY_OBJECT_CROP_REDUCTION_RATIO
        and object_area_ratio < MIN_OBJECT_AREA_RATIO_FOR_AGGRESSIVE_CROP
    ):
        return full_box
    return crop_box


def _score_classical_result(
    *,
    original_size: tuple[int, int],
    detected_box: ImageBox | None,
    crop_box: ImageBox,
    output_size: tuple[int, int],
) -> _CleanupScores:
    output_width, output_height = output_size
    output_area = _image_area(output_size)
    original_area = _image_area(original_size)
    crop_area = _box_area(crop_box)
    crop_reduction_ratio = 1.0 - (crop_area / original_area)
    aspect_ratio = output_width / output_height if output_height else 0
    dimensions_sane = output_width > 0 and output_height > 0 and output_area > 0
    aspect_sane = EXPECTED_MIN_ASPECT_RATIO <= aspect_ratio <= EXPECTED_MAX_ASPECT_RATIO

    object_area_ratio = 0.0
    if detected_box is not None:
        object_area_ratio = _box_area(detected_box) / original_area

    confidence = 0.25
    if dimensions_sane:
        confidence += 0.15
    if detected_box is not None:
        confidence += 0.22
    if 0.02 <= object_area_ratio <= 0.96:
        confidence += 0.15
    elif 0.005 <= object_area_ratio <= 0.98:
        confidence += 0.07
    if aspect_sane:
        confidence += 0.12
    if crop_reduction_ratio <= 0.75:
        confidence += 0.08
    elif crop_reduction_ratio <= 0.88:
        confidence += 0.04
    if crop_reduction_ratio >= MIN_CROP_REDUCTION_RATIO:
        confidence += 0.05

    quality = _heuristic_quality_score(output_width, output_height) or 0.45
    if aspect_sane:
        quality += 0.08
    else:
        quality -= 0.12
    if 0.04 <= object_area_ratio <= 0.88:
        quality += 0.10
    elif detected_box is None or object_area_ratio < 0.01:
        quality -= 0.18
    if crop_reduction_ratio > 0.88:
        quality -= 0.12
    elif crop_reduction_ratio >= MIN_CROP_REDUCTION_RATIO:
        quality += 0.04

    if detected_box is None:
        confidence = min(confidence, 0.55)
        quality = min(quality, 0.60)

    return _CleanupScores(
        confidence_score=_clamp_score(confidence),
        quality_score=_clamp_score(quality),
    )


def _alpha_mask(image: Image.Image) -> Image.Image | None:
    if image.mode != "RGBA":
        return None
    return image.getchannel("A").point(
        lambda value: 255 if value > ALPHA_CONTENT_THRESHOLD else 0
    )


def _near_white_foreground_mask(image: Image.Image) -> Image.Image:
    rgb = image.convert("RGB")
    white = Image.new("RGB", image.size, (255, 255, 255))
    delta = ImageChops.difference(rgb, white).convert("L")
    return delta.point(lambda value: 255 if value > WHITE_DELTA_THRESHOLD else 0)


def _edge_foreground_mask(image: Image.Image) -> Image.Image:
    edges = image.convert("RGB").convert("L").filter(ImageFilter.FIND_EDGES)
    return edges.point(lambda value: 255 if value > EDGE_DELTA_THRESHOLD else 0)


def _padding_for_box(image: Image.Image, box: ImageBox) -> int:
    content_edge = max(box[2] - box[0], box[3] - box[1])
    image_edge = min(image.width, image.height)
    min_padding = max(1, int(round(image_edge * MIN_PADDING_RATIO)))
    max_padding = max(min_padding, int(round(image_edge * MAX_PADDING_RATIO)))
    padding = int(round(content_edge * PADDING_RATIO))
    return max(min_padding, min(max_padding, padding))


def _union_boxes(boxes: list[ImageBox]) -> ImageBox:
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def _full_box(image: Image.Image) -> ImageBox:
    return (0, 0, image.width, image.height)


def _image_area(size: tuple[int, int]) -> int:
    return max(1, int(size[0]) * int(size[1]))


def _box_area(box: ImageBox) -> int:
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def _clamp_score(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 3)
