"""Provider contracts for product image processing."""

from __future__ import annotations

import asyncio
import os
import signal
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from functools import lru_cache, partial
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError, features

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
YANDEX_FEED_CANVAS_SIZE = (800, 800)
YANDEX_FEED_JPEG_QUALITY = 85
YANDEX_FEED_PREPROCESS_MAX_EDGE = 1600
YANDEX_FEED_PREPROCESS_TIMEOUT_SECONDS = 30
MAX_SOURCE_PIXELS = 40_000_000
MAX_YANDEX_FEED_SOURCE_PIXELS = 70_000_000
BACKGROUND_REMOVAL_PROVIDER_ENV = "BACKGROUND_REMOVAL_PROVIDER"
BACKGROUND_REMOVAL_REMBG_MODEL_ENV = "BACKGROUND_REMOVAL_REMBG_MODEL"
BACKGROUND_REMOVAL_REMBG_PRELOAD_MODELS_ENV = "BACKGROUND_REMOVAL_REMBG_PRELOAD_MODELS"
BACKGROUND_REMOVAL_REMBG_PROCESS_MODE_ENV = "BACKGROUND_REMOVAL_REMBG_PROCESS_MODE"
BACKGROUND_REMOVAL_TIMEOUT_ENV = "BACKGROUND_REMOVAL_TIMEOUT_SECONDS"
BACKGROUND_REMOVAL_COMMAND_ENVS = {
    ProductImageProcessingProvider.BIREFNET.value: "BACKGROUND_REMOVAL_BIREFNET_COMMAND",
    ProductImageProcessingProvider.BEN.value: "BACKGROUND_REMOVAL_BEN_COMMAND",
}
DEFAULT_BACKGROUND_REMOVAL_PROVIDER = ProductImageProcessingProvider.REMBG.value
DEFAULT_BACKGROUND_REMOVAL_REMBG_MODEL = "u2net"
DEFAULT_BACKGROUND_REMOVAL_REMBG_PROCESS_MODE = "experimental"
DEFAULT_BACKGROUND_REMOVAL_TIMEOUT_SECONDS = 120
SAFE_REMBG_MODEL_OPTIONS = [
    {
        "value": "u2net",
        "label": "U2Net",
        "description": "Stable baseline model for the first comparison pass.",
        "recommended": True,
    },
]
EXPERIMENTAL_REMBG_MODEL_OPTIONS = [
    {
        "value": "isnet-general-use",
        "label": "ISNet general",
        "description": "Often handles complex edges and light products more carefully.",
        "recommended": False,
    },
    {
        "value": "birefnet-general-lite",
        "label": "BiRefNet lite",
        "description": "Faster BiRefNet candidate for quality comparison.",
        "recommended": False,
    },
    {
        "value": "birefnet-general",
        "label": "BiRefNet general",
        "description": "High-quality general model, usually heavier than lite.",
        "recommended": False,
    },
    {
        "value": "birefnet-massive",
        "label": "BiRefNet massive",
        "description": "Heavy model candidate for difficult product images.",
        "recommended": False,
    },
    {
        "value": "bria-rmbg",
        "label": "BRIA RMBG",
        "description": "Additional strong candidate for transparency A/B testing.",
        "recommended": False,
    },
]
REMBG_MODEL_OPTIONS = [*SAFE_REMBG_MODEL_OPTIONS, *EXPERIMENTAL_REMBG_MODEL_OPTIONS]
DEFAULT_REMBG_PRELOAD_MODELS = tuple(item["value"] for item in SAFE_REMBG_MODEL_OPTIONS)


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

    def __init__(self, *, model_name: str | None = None) -> None:
        self.model_name = _background_removal_rembg_model(model_name)
        self.provider_name = f"{ProductImageProcessingProvider.REMBG.value}:{self.model_name}"

    async def process(
        self,
        *,
        source_content: bytes,
        context: ProductImageProcessingContext,
    ) -> ProductImageProcessingResult:
        timeout_seconds = _background_removal_timeout_seconds()
        if _should_run_rembg_in_subprocess(self.model_name):
            output = await asyncio.to_thread(
                _run_rembg_subprocess,
                model_name=self.model_name,
                source_content=source_content,
                timeout_seconds=timeout_seconds,
            )
            return _process_image_bytes(output, context=context)

        try:
            from rembg import remove  # type: ignore
        except ImportError as exc:
            raise RuntimeError("rembg provider is not installed") from exc

        session = _get_rembg_session(self.model_name)
        try:
            output = await asyncio.wait_for(
                asyncio.to_thread(partial(remove, source_content, session=session)),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise RuntimeError(
                f"rembg provider timed out after {timeout_seconds}s: {self.model_name}"
            ) from exc
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

            command = _render_command_argv(
                command_template,
                input_path=input_path,
                output_path=output_path,
            )
            try:
                completed = _run_command_with_timeout(
                    command,
                    timeout=self.timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    f"{self.provider_name} provider timed out after {self.timeout_seconds}s"
                ) from exc
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


def get_product_image_processor(
    provider: str,
    *,
    rembg_model: str | None = None,
) -> ProductImageProcessor:
    normalized_provider = resolve_background_removal_provider(provider)
    if normalized_provider == ProductImageProcessingProvider.AUTO.value:
        normalized_provider = DEFAULT_BACKGROUND_REMOVAL_PROVIDER
    if normalized_provider == ProductImageProcessingProvider.NOOP.value:
        return NoopProductImageProcessor()
    if normalized_provider == ProductImageProcessingProvider.MANUAL.value:
        return ManualProductImageProcessor()
    if normalized_provider == ProductImageProcessingProvider.REMBG.value:
        return RembgProductImageProcessor(model_name=rembg_model)
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
            "description": f"Python rembg package, model via {BACKGROUND_REMOVAL_REMBG_MODEL_ENV}",
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


def rembg_model_options(*, include_experimental: bool = False) -> list[dict[str, Any]]:
    options = REMBG_MODEL_OPTIONS if include_experimental else SAFE_REMBG_MODEL_OPTIONS
    return [dict(item) for item in options]


def default_rembg_model_name() -> str:
    return _background_removal_rembg_model()


def rembg_process_mode() -> str:
    return _background_removal_rembg_process_mode()


def rembg_preload_model_names(raw_value: str | None = None) -> list[str]:
    configured = (
        raw_value
        if raw_value is not None
        else os.getenv(BACKGROUND_REMOVAL_REMBG_PRELOAD_MODELS_ENV, "")
    ).strip()
    if not configured:
        return list(DEFAULT_REMBG_PRELOAD_MODELS)

    known = {item["value"] for item in REMBG_MODEL_OPTIONS}
    model_names: list[str] = []
    for item in configured.split(","):
        model_name = item.strip()
        if not model_name or model_name in model_names:
            continue
        if model_name not in known:
            raise ValueError(f"Unsupported rembg preload model: {model_name}")
        model_names.append(model_name)
    return model_names


def warmup_rembg_models(model_names: list[str] | None = None) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for model_name in model_names or rembg_preload_model_names():
        try:
            _get_rembg_session(model_name)
            results.append({"model": model_name, "status": "ready"})
        except Exception as exc:
            results.append({"model": model_name, "status": "error", "error": str(exc)})
    return results


def _background_removal_timeout_seconds() -> int:
    raw_value = os.getenv(BACKGROUND_REMOVAL_TIMEOUT_ENV, "").strip()
    if not raw_value:
        return DEFAULT_BACKGROUND_REMOVAL_TIMEOUT_SECONDS
    try:
        return max(1, int(raw_value))
    except ValueError:
        return DEFAULT_BACKGROUND_REMOVAL_TIMEOUT_SECONDS


def _background_removal_rembg_process_mode() -> str:
    requested = os.getenv(
        BACKGROUND_REMOVAL_REMBG_PROCESS_MODE_ENV,
        DEFAULT_BACKGROUND_REMOVAL_REMBG_PROCESS_MODE,
    ).strip().lower()
    if requested in {"always", "experimental", "never"}:
        return requested
    return DEFAULT_BACKGROUND_REMOVAL_REMBG_PROCESS_MODE


def _background_removal_rembg_model(model_name: str | None = None) -> str:
    requested = (model_name or os.getenv(BACKGROUND_REMOVAL_REMBG_MODEL_ENV, "")).strip()
    return requested or DEFAULT_BACKGROUND_REMOVAL_REMBG_MODEL


def _should_run_rembg_in_subprocess(model_name: str) -> bool:
    mode = _background_removal_rembg_process_mode()
    if mode == "always":
        return True
    if mode == "never":
        return False

    safe_models = {item["value"] for item in SAFE_REMBG_MODEL_OPTIONS}
    return model_name not in safe_models


def _run_rembg_subprocess(
    *,
    model_name: str,
    source_content: bytes,
    timeout_seconds: int,
) -> bytes:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "rembg_remove.py"
    if not script_path.exists():
        raise RuntimeError("rembg subprocess runner is not available")

    with tempfile.TemporaryDirectory(prefix="rembg-bg-") as tmp_dir:
        input_path = os.path.join(tmp_dir, "input.bin")
        output_path = os.path.join(tmp_dir, "output.png")
        with open(input_path, "wb") as input_file:
            input_file.write(source_content)

        command = [
            sys.executable,
            str(script_path),
            "--model",
            model_name,
            "--input",
            input_path,
            "--output",
            output_path,
        ]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"rembg subprocess timed out after {timeout_seconds}s: {model_name}"
            ) from exc

        if completed.returncode != 0:
            stderr = (completed.stderr or completed.stdout or "").strip()
            detail = f": {stderr[:500]}" if stderr else ""
            raise RuntimeError(f"rembg subprocess failed for {model_name}{detail}")
        if not os.path.exists(output_path):
            raise RuntimeError(f"rembg subprocess did not create output image: {model_name}")
        with open(output_path, "rb") as output_file:
            return output_file.read()


def _render_command_argv(
    command_template: str,
    *,
    input_path: str,
    output_path: str,
) -> list[str]:
    if "{input}" not in command_template or "{output}" not in command_template:
        raise RuntimeError("Background-removal command must contain {input} and {output}")

    try:
        template_argv = shlex.split(command_template, posix=os.name != "nt")
        command = [
            part.format(input=input_path, output=output_path)
            for part in template_argv
        ]
    except (KeyError, ValueError) as exc:
        raise RuntimeError("Background-removal command template is invalid") from exc

    if not command or not command[0].strip():
        raise RuntimeError("Background-removal command is empty")
    return command


def _run_command_with_timeout(
    command: list[str],
    *,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _terminate_process(process)
        stdout, stderr = process.communicate()
        raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr)

    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _terminate_process(process: subprocess.Popen[str]) -> None:
    try:
        if os.name != "nt":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        return


@lru_cache(maxsize=8)
def _get_rembg_session(model_name: str):
    try:
        from rembg import new_session  # type: ignore
    except ImportError as exc:
        raise RuntimeError("rembg provider is not installed") from exc

    try:
        return new_session(model_name)
    except Exception as exc:
        raise RuntimeError(
            f"rembg model is not configured correctly: {model_name}"
        ) from exc


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
    max_source_pixels = (
        MAX_YANDEX_FEED_SOURCE_PIXELS
        if variant_type == ProductImageVariantType.YANDEX_FEED.value
        else MAX_SOURCE_PIXELS
    )
    if variant_type == ProductImageVariantType.YANDEX_FEED.value:
        source_content = _preprocess_large_yandex_feed_source(source_content)
    preprocess_max_edge = (
        YANDEX_FEED_PREPROCESS_MAX_EDGE
        if variant_type == ProductImageVariantType.YANDEX_FEED.value
        else None
    )
    image = _open_source_image(
        source_content,
        max_source_pixels=max_source_pixels,
        preprocess_max_edge=preprocess_max_edge,
    )
    image = _trim_transparent_borders(image)

    if variant_type == ProductImageVariantType.YANDEX_FEED.value:
        image = _normalize_yandex_feed_canvas(image)
        content = _export_yandex_feed_jpeg(image)
        return ProductImageProcessingResult(
            content=content,
            extension="jpg",
            width=image.width,
            height=image.height,
        )
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


def _open_source_image(
    source_content: bytes,
    *,
    max_source_pixels: int = MAX_SOURCE_PIXELS,
    preprocess_max_edge: int | None = None,
) -> Image.Image:
    if not source_content:
        raise ValueError("Source image is empty")

    try:
        with Image.open(BytesIO(source_content)) as image:
            if image.width * image.height > max_source_pixels:
                raise ValueError("Source image is too large for safe processing")
            if preprocess_max_edge and max(image.width, image.height) > preprocess_max_edge:
                image.thumbnail(
                    (preprocess_max_edge, preprocess_max_edge),
                    Image.Resampling.LANCZOS,
                    reducing_gap=3.0,
                )
            transposed = ImageOps.exif_transpose(image)
            srgb = _convert_to_srgb(transposed)
            converted = srgb.convert("RGBA" if _has_alpha(srgb) else "RGB")
            converted.load()
            return converted.copy()
    except UnidentifiedImageError as exc:
        raise ValueError("Source image cannot be opened by Pillow") from exc


def _preprocess_large_yandex_feed_source(source_content: bytes) -> bytes:
    if not source_content:
        raise ValueError("Source image is empty")

    try:
        with Image.open(BytesIO(source_content)) as image:
            source_pixels = image.width * image.height
    except UnidentifiedImageError as exc:
        raise ValueError("Source image cannot be opened by Pillow") from exc

    if source_pixels > MAX_YANDEX_FEED_SOURCE_PIXELS:
        raise ValueError("Source image is too large for safe processing")
    if source_pixels <= MAX_SOURCE_PIXELS:
        return source_content

    with tempfile.TemporaryDirectory(prefix="yandex-feed-source-") as tmp_dir:
        input_path = os.path.join(tmp_dir, "input.bin")
        output_path = os.path.join(tmp_dir, "output.png")
        with open(input_path, "wb") as input_file:
            input_file.write(source_content)

        command = [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            input_path,
            "-vf",
            (
                f"scale={YANDEX_FEED_PREPROCESS_MAX_EDGE}:"
                f"{YANDEX_FEED_PREPROCESS_MAX_EDGE}:"
                "force_original_aspect_ratio=decrease"
            ),
            "-frames:v",
            "1",
            "-map_metadata",
            "-1",
            output_path,
        ]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=YANDEX_FEED_PREPROCESS_TIMEOUT_SECONDS,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "ffmpeg is required to safely process this legacy source image"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "Legacy source image preprocessing timed out"
            ) from exc

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            suffix = f": {detail[:500]}" if detail else ""
            raise RuntimeError(f"Legacy source image preprocessing failed{suffix}")
        if not os.path.exists(output_path):
            raise RuntimeError("Legacy source image preprocessing produced no output")
        with open(output_path, "rb") as output_file:
            output = output_file.read()
        if not output:
            raise RuntimeError("Legacy source image preprocessing produced empty output")
        return output


def _has_alpha(image: Image.Image) -> bool:
    return image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in image.info
    )


def _convert_to_srgb(image: Image.Image) -> Image.Image:
    icc_profile = image.info.get("icc_profile")
    if not icc_profile:
        return image
    try:
        source_profile = ImageCms.ImageCmsProfile(BytesIO(icc_profile))
        target_profile = ImageCms.createProfile("sRGB")
        if _has_alpha(image):
            rgba = image.convert("RGBA")
            alpha = rgba.getchannel("A")
            converted = ImageCms.profileToProfile(
                rgba.convert("RGB"),
                source_profile,
                target_profile,
                outputMode="RGB",
            )
            converted.putalpha(alpha)
            return converted
        return ImageCms.profileToProfile(
            image.convert("RGB"),
            source_profile,
            target_profile,
            outputMode="RGB",
        )
    except (OSError, TypeError, ValueError):
        return image


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


def _normalize_yandex_feed_canvas(image: Image.Image) -> Image.Image:
    source = _ensure_rgba(_trim_transparent_borders(image))
    canvas_width, canvas_height = YANDEX_FEED_CANVAS_SIZE
    fitted = _resize_to_box(
        source,
        max_width=canvas_width,
        max_height=canvas_height,
        allow_upscale=False,
    )
    canvas = Image.new("RGB", YANDEX_FEED_CANVAS_SIZE, (255, 255, 255))
    offset = (
        (canvas_width - fitted.width) // 2,
        (canvas_height - fitted.height) // 2,
    )
    if fitted.mode == "RGBA":
        canvas.paste(fitted, box=offset, mask=fitted.getchannel("A"))
    else:
        canvas.paste(fitted.convert("RGB"), box=offset)
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


def _resize_to_box(
    image: Image.Image,
    *,
    max_width: int,
    max_height: int,
    allow_upscale: bool = True,
) -> Image.Image:
    scale = min(max_width / image.width, max_height / image.height)
    if not allow_upscale:
        scale = min(scale, 1.0)
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


def _export_yandex_feed_jpeg(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.convert("RGB").save(
        buffer,
        format="JPEG",
        quality=YANDEX_FEED_JPEG_QUALITY,
        optimize=True,
        progressive=True,
        subsampling=2,
    )
    return buffer.getvalue()
