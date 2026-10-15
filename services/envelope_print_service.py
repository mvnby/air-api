"""Stateless DL printing: no customer edits or business-document lifecycle."""

from __future__ import annotations

import base64
import binascii
import re
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Literal
from xml.sax.saxutils import escape

from pydantic import BaseModel, ConfigDict, Field, field_validator
from PIL import Image, UnidentifiedImageError
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph

from services.postal_address_service import PostalAddressLines, normalize_postal_address


class EnvelopeParty(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(min_length=1, max_length=300)
    address: str = Field(min_length=1, max_length=600)
    postal_code: str = Field(pattern=r"^[0-9]{6}$")

    @field_validator("name", "address")
    @classmethod
    def printable_text(cls, value: str) -> str:
        if any(ord(char) < 32 and not char.isspace() for char in value):
            raise ValueError("Недопустимые символы в адресных данных")
        return " ".join(value.split())

    @field_validator("address", mode="before")
    @classmethod
    def preserve_address_lines(cls, value: str) -> str:
        # Turn pasted line breaks into delimiters before whitespace is collapsed.
        return ", ".join(line for line in value.splitlines() if line.strip()) if isinstance(value, str) else value


class EnvelopeBranding(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(default="", max_length=100)
    logo_data_url: str | None = Field(default=None, max_length=350_000, pattern=r"^data:image/(?:png|jpeg);base64,[A-Za-z0-9+/=]+$")

    _printable_name = field_validator("name")(EnvelopeParty.printable_text.__func__)


class EnvelopePrintPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["DL"] = "DL"
    sender: EnvelopeParty
    recipient: EnvelopeParty
    branding: EnvelopeBranding | None = None


class EnvelopePreviewResponse(BaseModel):
    sender: PostalAddressLines
    recipient: PostalAddressLines


def preview_envelope(payload: EnvelopePrintPayload) -> EnvelopePreviewResponse:
    return EnvelopePreviewResponse(**{
        key: normalize_postal_address(party.address, party.postal_code)
        for key, party in (("sender", payload.sender), ("recipient", payload.recipient))
    })


@lru_cache(maxsize=2)
def _font_name(bold: bool = False) -> str:
    # The production image installs fonts-dejavu-core. macOS paths support local QA.
    candidates = (
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
        f"/opt/homebrew/share/fonts/DejaVuSans{'-Bold' if bold else ''}.ttf",
        f"/System/Library/Fonts/Supplemental/Arial{' Bold' if bold else ''}.ttf",
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            name = "EnvelopeSansBold" if bold else "EnvelopeSans"
            pdfmetrics.registerFont(TTFont(name, candidate))
            return name
    raise RuntimeError("Не найден шрифт для печати конверта")


def _draw_party(
    canvas: Canvas, party: EnvelopeParty, *, label: str, x: float, top: float,
    width: float, height: float, font: str, bottom: float | None = None,
) -> None:
    address = normalize_postal_address(party.address, party.postal_code)
    if any(code != party.postal_code for code in re.findall(r"(?<!\d)\d{6}(?!\d)", party.address)):
        raise ValueError(f"{label}: индекс в адресе отличается от отдельного поля. Исправьте индекс.")
    bold = _font_name(True)
    paragraphs: list[Paragraph] = []
    for font_size in (10, 9.5, 9, 8.5):
        style = ParagraphStyle(
            "envelope", fontName=font, fontSize=font_size, leading=font_size * 1.22,
            splitLongWords=True,
        )
        name_style = ParagraphStyle("name", parent=style, fontName=bold)
        postal_line = escape(address.postal_line).replace(
            party.postal_code, f'<font name="{bold}" size="{font_size + 1.5}">{party.postal_code}</font>', 1,
        )
        paragraphs = [Paragraph(escape(party.name), name_style)]
        paragraphs += [Paragraph(escape(line), style) for line in address.delivery_lines]
        paragraphs += [Paragraph(postal_line, ParagraphStyle("postcode", parent=style, leading=(font_size + 1.5) * 1.22))]
        paragraphs += [Paragraph(escape(line), style) for line in [*address.area_lines, address.country]]
        sizes = [paragraph.wrap(width, height)[1] for paragraph in paragraphs]
        gap = .6 * mm
        total_height = sum(sizes) + gap * (len(sizes) - 1)
        if total_height <= height:
            break
    else:
        raise ValueError(f"{label}: текст не помещается на конверте DL. Сократите название или адрес.")

    if bottom is not None:
        top = bottom + total_height
    canvas.setFont(font, 7)
    canvas.drawString(x, top + 3 * mm, label)
    cursor = top
    for paragraph, paragraph_height in zip(paragraphs, sizes):
        cursor -= paragraph_height
        paragraph.drawOn(canvas, x, cursor)
        cursor -= gap


def _draw_branding(canvas: Canvas, branding: EnvelopeBranding, font: str) -> None:
    x, bottom, width, height = 8 * mm, 15 * mm, 82 * mm, 18 * mm
    if branding.logo_data_url:
        try:
            data = base64.b64decode(branding.logo_data_url.split(",", 1)[1], validate=True)
            if len(data) > 256 * 1024:
                raise ValueError("Логотип: файл должен быть не больше 256 КБ")
            with Image.open(BytesIO(data)) as logo:
                if logo.format not in ("PNG", "JPEG") or max(logo.size) > 2000 or min(logo.size) < 1:
                    raise ValueError("Логотип: нужен PNG или JPEG размером до 2000 × 2000 пикселей")
                logo.load()
                scale = min(24 * mm / logo.width, height / logo.height)
                logo_width, logo_height = logo.width * scale, logo.height * scale
                canvas.drawImage(ImageReader(logo), x, bottom + (height - logo_height) / 2,
                                 width=logo_width, height=logo_height, mask="auto")
            x += 28 * mm
            width -= 28 * mm
        except (binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise ValueError("Не удалось прочитать логотип. Выберите PNG или JPEG.") from exc
    if branding.name:
        paragraph = Paragraph(escape(branding.name), ParagraphStyle(
            "branding", fontName=font, fontSize=9, leading=11,
        ))
        _, text_height = paragraph.wrap(width, height)
        if text_height > height:
            raise ValueError("Название рядом с логотипом не помещается. Сократите его.")
        paragraph.drawOn(canvas, x, bottom + (height - text_height) / 2)


def render_envelope_pdf(payload: EnvelopePrintPayload) -> bytes:
    """One landscape 220 x 110 mm page with embedded Cyrillic and blank stamp zone."""
    output = BytesIO()
    canvas = Canvas(output, pagesize=(220 * mm, 110 * mm), pageCompression=1)
    canvas.setTitle("Конверт DL")
    canvas.setAuthor("Kitlane")
    font = _font_name()
    _draw_party(canvas, payload.sender, label="Отправитель", x=8 * mm,
                top=97 * mm, width=94 * mm, height=37 * mm, font=font)
    _draw_party(canvas, payload.recipient, label="Получатель", x=110 * mm,
                top=54 * mm, width=102 * mm, height=40 * mm, bottom=14 * mm, font=font)
    if payload.branding:
        _draw_branding(canvas, payload.branding, _font_name(True))
    canvas.showPage()
    canvas.save()
    return output.getvalue()
