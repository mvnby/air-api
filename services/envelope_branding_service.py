"""Bounded, embedded envelope branding shared by issuer settings and PDF printing."""

import base64
import binascii
from io import BytesIO
from typing import Any

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, field_validator


def printable_envelope_text(value: str) -> str:
    if any(ord(char) < 32 and not char.isspace() for char in value):
        raise ValueError("Недопустимые символы в адресных данных")
    return " ".join(value.split())


class EnvelopeBranding(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(default="", max_length=100)
    logo_data_url: str | None = Field(default=None, max_length=350_000, pattern=r"^data:image/(?:png|jpeg);base64,[A-Za-z0-9+/=]+$")

    _printable_name = field_validator("name")(printable_envelope_text)


def envelope_logo_bytes(data_url: str) -> bytes:
    try:
        data = base64.b64decode(data_url.split(",", 1)[1], validate=True)
        if len(data) > 256 * 1024:
            raise ValueError("Логотип: файл должен быть не больше 256 КБ")
        with Image.open(BytesIO(data)) as logo:
            if logo.format not in ("PNG", "JPEG") or max(logo.size) > 2000 or min(logo.size) < 1:
                raise ValueError("Логотип: нужен PNG или JPEG размером до 2000 × 2000 пикселей")
            logo.load()
        return data
    except (binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Не удалось прочитать логотип. Выберите PNG или JPEG.") from exc


def validated_envelope_branding(value: Any) -> dict[str, Any]:
    branding = EnvelopeBranding.model_validate(value)
    if branding.logo_data_url:
        envelope_logo_bytes(branding.logo_data_url)
    return branding.model_dump()
