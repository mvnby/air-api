"""Bounded content validation for untrusted public image uploads."""

from __future__ import annotations

import asyncio
import io
import warnings

from PIL import Image, UnidentifiedImageError


PUBLIC_IMAGE_FORMAT_BY_MIME = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}


async def validate_public_image(
    *,
    filename: str,
    content_type: str,
    content: bytes,
    max_bytes: int,
) -> None:
    normalized_filename = str(filename or "image")[:255]
    normalized_mime = str(content_type or "").split(";", 1)[0].strip().lower()
    byte_limit = max(1, int(max_bytes))
    if normalized_mime not in PUBLIC_IMAGE_FORMAT_BY_MIME:
        raise ValueError(
            f"{normalized_filename}: поддерживаются только JPEG, PNG и WebP"
        )
    if not content:
        raise ValueError(f"{normalized_filename}: файл пуст")
    if len(content) > byte_limit:
        raise ValueError(
            f"{normalized_filename}: размер не должен превышать "
            f"{byte_limit // (1024 * 1024)} МБ"
        )

    def verify() -> str:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                image.verify()
                return str(image.format or "").upper()

    try:
        detected_format = await asyncio.to_thread(verify)
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValueError(
            f"{normalized_filename}: файл не является корректным изображением"
        ) from exc
    if detected_format != PUBLIC_IMAGE_FORMAT_BY_MIME[normalized_mime]:
        raise ValueError(
            f"{normalized_filename}: содержимое файла не соответствует типу "
            f"{normalized_mime}"
        )
