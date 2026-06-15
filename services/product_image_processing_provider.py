"""Provider contracts for product image processing."""

from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
import tempfile
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
BACKGROUND_REMOVAL_PROVIDER_ENV = "BACKGROUND_REMOVAL_PROVIDER"
BACKGROUND_REMOVAL_TIMEOUT_ENV = "BACKGROUND_REMOVAL_TIMEOUT_SECONDS"
BACKGROUND_REMOVAL_COMMAND_ENVS = {
    ProductImageProcessingProvider.BIREFNET.value: "BACKGROUND_REMOVAL_BIREFNET_COMMAND",
    ProductImageProcessingProvider.BEN.value: "BACKGROUND_REMOVAL_BEN_COMMAND",
}
DEFAULT_BACKGROUND_REMOVAL_PROVIDER = ProductImageProcessingProvider.REMBG.value
DEFAULT_BACKGROUND_REMOVAL_TIMEOUT_SECONDS = 120


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


class CommandProductImageProcessor:
    """Adapter for model runners wired by env command templates.

    The command receives `{input}` and `{output}` placeholders. This lets ops test
    BEN, BiRefNet, or any local/remote wrapper without changing the app contract.
    """

    def __init__(
        self,
        *,
        provider_name: str,
        command_env: str,
        timeout_seconds: int | None = None,
    ):
        self.provider_name = provider_name
        self.command_env = command_env
        self.timeout_seconds = timeout_seconds or _background_removal_timeout_seconds()

    async def process(
        self,
        *,
        source_content: bytes,
        context: ProductImageProcessingContext,
    ) -> ProductImageProcessingResult:
        command_template = os.getenv(self.command_env, "").strip()
        if not command_template:
            raise RuntimeError(
                f"{self.provider_name} provider is not configured: set {self.command_env}"
            )

        output = await asyncio.to_thread(
            self._run_command,
            command_template,
            source_content,
        )
        return _process_image_bytes(output, context=context)

    def _run_command(self, command_template: str, source_content: bytes) -> bytes:
        with tempfile.TemporaryDirectory(prefix=f"{self.provider_name}-bg-") as tmp_dir:
            input_path = os.path.join(tmp_dir, "input.png")
            output_path = os.path.join(tmp_dir, "output.png")
            with open(input_path, "wb") as input_file:
                input_file.write(source_content)

            command = command_template.format(
                input=shlex.quote(input_path),
                output=shlex.quote(output_path),
            )
            completed = subprocess.run(
                command,
                shell=True,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
            if completed.returncode != 0:
                stderr = (completed.stderr or completed.stdout or "").strip()
                detail = f": {stderr[:500]}" if stderr else ""
                raise RuntimeError(f"{self.provider_name} provider failed{detail}")
            if not os.path.exists(output_path):
                raise RuntimeError(
                    f"{self.provider_name} provider did not create output image"
                )
            with open(output_path, "rb") as output_file:
                return output_file.read()


class BiRefNetProductImageProcessor(CommandProductImageProcessor):
    def __init__(self):
        super().__init__(
            provider_name=ProductImageProcessingProvider.BIREFNET.value,
            command_env=BACKGROUND_REMOVAL_COMMAND_ENVS[
                ProductImageProcessingProvider.BIREFNET.value
            ],
        )


class BenProductImageProcessor(CommandProductImageProcessor):
    def __init__(self):
        super().__init__(
            provider_name=ProductImageProcessingProvider.BEN.value,
            command_env=BACKGROUND_REMOVAL_COMMAND_ENVS[ProductImageProcessingProvider.BEN.value],
        )


def get_product_image_processor(provider: str) -> ProductImageProcessor:
    normalized_provider = resolve_background_removal_provider(provider)
    if normalized_provider == ProductImageProcessingProvider.AUTO.value:
        normalized_provider = DEFAULT_BACKGROUND_REMOVAL_PROVIDER
    if normalized_provider == ProductImageProcessingProvider.NOOP.value:
        return NoopProductImageProcessor()
    if normalized_provider == ProductImageProcessingProvider.MANUAL.value:
        return ManualProductImageProcessor()
    if normalized_provider == ProductImageProcessingProvider.REMBG.value:
        return RembgProductImageProcessor()
    if normalized_provider == ProductImageProcessingProvider.BIREFNET.value:
        return BiRefNetProductImageProcessor()
    if normalized_provider == ProductImageProcessingProvider.BEN.value:
        return BenProductImageProcessor()
    raise ValueError(f"Unsupported image processing provider={provider!r}")


def resolve_background_removal_provider(provider: str | None) -> str:
    requested = (provider or ProductImageProcessingProvider.AUTO.value).strip().lower()
    if requested != ProductImageProcessingProvider.AUTO.value:
        return requested

    configured = os.getenv(
        BACKGROUND_REMOVAL_PROVIDER_ENV,
        DEFAULT_BACKGROUND_REMOVAL_PROVIDER,
    ).strip().lower()
    if not configured or configured == ProductImageProcessingProvider.AUTO.value:
        return DEFAULT_BACKGROUND_REMOVAL_PROVIDER
    return configured


def background_removal_provider_options() -> list[dict[str, str]]:
    return [
        {
            "value": ProductImageProcessingProvider.AUTO.value,
            "label": "auto",
            "description": f"Use {BACKGROUND_REMOVAL_PROVIDER_ENV}, default rembg",
        },
        {
            "value": ProductImageProcessingProvider.NOOP.value,
            "label": "noop",
            "description": "Normalize image without background removal",
        },
        {
            "value": ProductImageProcessingProvider.MANUAL.value,
            "label": "manual",
            "description": "Manual/operator-approved processing alias",
        },
        {
            "value": ProductImageProcessingProvider.REMBG.value,
            "label": "rembg",
            "description": "Python rembg package",
        },
        {
            "value": ProductImageProcessingProvider.BIREFNET.value,
            "label": "BiRefNet",
            "description": f"Command adapter via {BACKGROUND_REMOVAL_COMMAND_ENVS['birefnet']}",
        },
        {
            "value": ProductImageProcessingProvider.BEN.value,
            "label": "BEN",
            "description": f"Command adapter via {BACKGROUND_REMOVAL_COMMAND_ENVS['ben']}",
        },
    ]


def _background_removal_timeout_seconds() -> int:
    raw_value = os.getenv(BACKGROUND_REMOVAL_TIMEOUT_ENV, "").strip()
    if not raw_value:
        return DEFAULT_BACKGROUND_REMOVAL_TIMEOUT_SECONDS
    try:
        return max(1, int(raw_value))
    except ValueError:
        return DEFAULT_BACKGROUND_REMOVAL_TIMEOUT_SECONDS


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
