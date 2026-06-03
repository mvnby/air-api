"""Provider contracts for product image processing."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Protocol

from PIL import Image, ImageOps, UnidentifiedImageError, features

from services.product_image_processing_contract import (
    ProductImageProcessingProvider,
    ProductImageVariantType,
)


# Storefront-facing sizes are intentionally conservative: product cards render
# around 640px wide today, while detail-gallery images benefit from extra DPR
# headroom without creating production-sized source mutations.
CARD_CANVAS_SIZE = (960, 960)
CARD_PADDING_RATIO = 0.08
PROCESSED_MAX_EDGE = 1600
FULL_MAX_EDGE = 1800
MAX_SOURCE_PIXELS = 40_000_000


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
    """Safe provider with no background removal, only classical normalization."""

    provider_name = ProductImageProcessingProvider.NOOP.value

    async def process(
        self,
        *,
        source_content: bytes,
        context: ProductImageProcessingContext,
    ) -> ProductImageProcessingResult:
        return _process_image_bytes(source_content, context=context)


class ManualProductImageProcessor(NoopProductImageProcessor):
    """Alias for operator-approved manual processing flows."""

    provider_name = ProductImageProcessingProvider.MANUAL.value


class RembgProductImageProcessor:
    """Optional provider; imports rembg lazily when explicitly selected."""

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
        return _process_image_bytes(output, context=context)


def get_product_image_processor(provider: str) -> ProductImageProcessor:
    if provider == ProductImageProcessingProvider.NOOP.value:
        return NoopProductImageProcessor()
    if provider == ProductImageProcessingProvider.MANUAL.value:
        return ManualProductImageProcessor()
    if provider == ProductImageProcessingProvider.REMBG.value:
        return RembgProductImageProcessor()
    raise ValueError(f"Unsupported image processing provider={provider!r}")


def _process_image_bytes(
    source_content: bytes,
    *,
    context: ProductImageProcessingContext | None,
) -> ProductImageProcessingResult:
    variant_type = (
        context.variant_type
        if context is not None
        else ProductImageVariantType.PROCESSED.value
    )
    image = _open_source_image(source_content)
    image = _trim_transparent_borders(image)

    if variant_type == ProductImageVariantType.CARD.value:
        image = _normalize_card_canvas(image)
    elif variant_type == ProductImageVariantType.FULL.value:
        image = _resize_to_max_edge(image, FULL_MAX_EDGE)
    else:
        image = _resize_to_max_edge(image, PROCESSED_MAX_EDGE)

    content, extension = _export_image(image)
    return ProductImageProcessingResult(
        content=content,
        extension=extension,
        width=image.width,
        height=image.height,
    )


def _open_source_image(source_content: bytes) -> Image.Image:
    if not source_content:
        raise ValueError("Source image is empty")

    try:
        with Image.open(BytesIO(source_content)) as image:
            if image.width * image.height > MAX_SOURCE_PIXELS:
                raise ValueError("Source image is too large for safe processing")
            transposed = ImageOps.exif_transpose(image)
            converted = transposed.convert("RGBA" if _has_alpha(transposed) else "RGB")
            converted.load()
            return converted.copy()
    except UnidentifiedImageError as exc:
        raise ValueError("Source image cannot be opened by Pillow") from exc


def _has_alpha(image: Image.Image) -> bool:
    return image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in image.info
    )


def _ensure_rgba(image: Image.Image) -> Image.Image:
    if image.mode == "RGBA":
        return image
    return image.convert("RGBA")


def _trim_transparent_borders(image: Image.Image) -> Image.Image:
    if image.mode != "RGBA":
        return image

    bbox = image.getchannel("A").getbbox()
    if not bbox:
        return image
    return image.crop(bbox)


def _normalize_card_canvas(image: Image.Image) -> Image.Image:
    image = _ensure_rgba(_trim_transparent_borders(image))
    canvas_width, canvas_height = CARD_CANVAS_SIZE
    padding = int(round(min(canvas_width, canvas_height) * CARD_PADDING_RATIO))
    max_width = max(1, canvas_width - padding * 2)
    max_height = max(1, canvas_height - padding * 2)

    fitted = _resize_to_box(image, max_width=max_width, max_height=max_height)
    canvas = Image.new("RGBA", CARD_CANVAS_SIZE, (255, 255, 255, 0))
    offset = (
        (canvas_width - fitted.width) // 2,
        (canvas_height - fitted.height) // 2,
    )
    canvas.alpha_composite(fitted, dest=offset)
    return canvas


def _resize_to_max_edge(image: Image.Image, max_edge: int) -> Image.Image:
    if max(image.width, image.height) <= max_edge:
        return image.copy()
    scale = max_edge / max(image.width, image.height)
    size = (
        max(1, int(round(image.width * scale))),
        max(1, int(round(image.height * scale))),
    )
    return image.resize(size, Image.Resampling.LANCZOS)


def _resize_to_box(image: Image.Image, *, max_width: int, max_height: int) -> Image.Image:
    scale = min(max_width / image.width, max_height / image.height)
    if scale == 1:
        return image.copy()
    size = (
        max(1, int(round(image.width * scale))),
        max(1, int(round(image.height * scale))),
    )
    return image.resize(size, Image.Resampling.LANCZOS)


def _export_image(image: Image.Image) -> tuple[bytes, str]:
    buffer = BytesIO()
    if features.check("webp"):
        image.save(buffer, format="WEBP", quality=88, method=6, exact=True)
        return buffer.getvalue(), "webp"

    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue(), "png"
