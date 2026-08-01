from __future__ import annotations

import io

import pytest
from PIL import Image

from core.public_image_validation import validate_public_image


def _image_bytes(image_format: str, *, size: tuple[int, int] = (2, 2)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color="white").save(buffer, format=image_format)
    return buffer.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("image_format", "content_type"),
    [
        ("JPEG", "image/jpeg"),
        ("PNG", "image/png"),
        ("WEBP", "image/webp"),
    ],
)
async def test_validate_public_image_accepts_tiny_matching_images(
    image_format,
    content_type,
):
    content = _image_bytes(image_format)

    await validate_public_image(
        filename=f"tiny.{image_format.lower()}",
        content_type=content_type,
        content=content,
        max_bytes=len(content),
    )


@pytest.mark.asyncio
async def test_validate_public_image_rejects_declared_mime_mismatch():
    with pytest.raises(ValueError, match="не соответствует типу"):
        await validate_public_image(
            filename="spoofed.jpg",
            content_type="image/jpeg",
            content=_image_bytes("PNG"),
            max_bytes=1024,
        )


@pytest.mark.asyncio
async def test_validate_public_image_rejects_corrupt_content():
    with pytest.raises(ValueError, match="корректным изображением"):
        await validate_public_image(
            filename="corrupt.png",
            content_type="image/png",
            content=b"not-a-real-image",
            max_bytes=1024,
        )


@pytest.mark.asyncio
async def test_validate_public_image_promotes_decompression_bomb_warning(
    monkeypatch,
):
    content = _image_bytes("PNG", size=(2, 1))
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1)

    with pytest.raises(ValueError, match="корректным изображением"):
        await validate_public_image(
            filename="bomb.png",
            content_type="image/png",
            content=content,
            max_bytes=1024,
        )


@pytest.mark.asyncio
async def test_validate_public_image_enforces_size_before_decode(monkeypatch):
    opened = False

    def must_not_open(*_args, **_kwargs):
        nonlocal opened
        opened = True
        raise AssertionError("oversized image reached Pillow")

    monkeypatch.setattr(Image, "open", must_not_open)
    with pytest.raises(ValueError, match="размер"):
        await validate_public_image(
            filename="large.png",
            content_type="image/png",
            content=b"12345",
            max_bytes=4,
        )
    assert opened is False
