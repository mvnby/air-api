"""Stateless DL printing: no customer edits or business-document lifecycle."""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Literal
from xml.sax.saxutils import escape

from pydantic import BaseModel, ConfigDict, Field, field_validator
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph


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


class EnvelopePrintPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["DL"] = "DL"
    sender: EnvelopeParty
    recipient: EnvelopeParty


@lru_cache(maxsize=1)
def _font_name() -> str:
    # The production image installs fonts-dejavu-core. macOS paths support local QA.
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/opt/homebrew/share/fonts/DejaVuSans.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            pdfmetrics.registerFont(TTFont("EnvelopeSans", candidate))
            return "EnvelopeSans"
    raise RuntimeError("Не найден шрифт для печати конверта")


def _draw_party(
    canvas: Canvas, party: EnvelopeParty, *, label: str, x: float, top: float,
    width: float, height: float, font: str,
) -> None:
    paragraphs: list[Paragraph] = []
    for font_size in (10, 9.5, 9, 8.5):
        style = ParagraphStyle(
            "envelope", fontName=font, fontSize=font_size, leading=font_size * 1.3,
            splitLongWords=True,
        )
        paragraphs = [Paragraph(escape(line), style) for line in (
            party.name, party.address, f"{party.postal_code}, Республика Беларусь",
        )]
        sizes = [paragraph.wrap(width, height)[1] for paragraph in paragraphs]
        if sum(sizes) + 4 * mm <= height:
            break
    else:
        raise ValueError(f"{label}: текст не помещается на конверте DL. Сократите название или адрес.")

    canvas.setFont(font, 7)
    canvas.drawString(x, top + 3 * mm, label)
    cursor = top
    for paragraph, paragraph_height in zip(paragraphs, sizes):
        cursor -= paragraph_height
        paragraph.drawOn(canvas, x, cursor)
        cursor -= 1.5 * mm


def render_envelope_pdf(payload: EnvelopePrintPayload) -> bytes:
    """One landscape 220 x 110 mm page with embedded Cyrillic and blank stamp zone."""
    output = BytesIO()
    canvas = Canvas(output, pagesize=(220 * mm, 110 * mm), pageCompression=1)
    canvas.setTitle("Конверт DL")
    canvas.setAuthor("Kitlane")
    font = _font_name()
    _draw_party(canvas, payload.sender, label="Отправитель", x=10 * mm,
                top=96 * mm, width=92 * mm, height=34 * mm, font=font)
    _draw_party(canvas, payload.recipient, label="Получатель", x=105 * mm,
                top=53 * mm, width=105 * mm, height=36 * mm, font=font)
    canvas.showPage()
    canvas.save()
    return output.getvalue()
