from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas

from modules.documents.application.facsimile_pdf import FacsimilePdfError, _overlay


def _pdf() -> bytes:
    output = BytesIO()
    canvas = Canvas(output, pagesize=(595, 842))
    canvas.drawString(50, 800, "Original document")
    canvas.save()
    return output.getvalue()


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGBA", (100, 50), (0, 0, 0, 128)).save(output, format="PNG")
    return output.getvalue()


def _placement(**changes):
    values = dict(page_number=1, signature_x_mm=20, signature_y_mm=20, signature_width_mm=40,
                  seal_x_mm=80, seal_y_mm=20, seal_width_mm=30)
    values.update(changes)
    return SimpleNamespace(**values)


def test_overlay_creates_a_valid_separate_pdf():
    original = _pdf()
    signed = _overlay(original, _png(), _png(), _placement())

    assert signed != original
    assert len(PdfReader(BytesIO(signed)).pages) == 1


def test_overlay_rejects_placement_outside_real_pdf_page():
    with pytest.raises(FacsimilePdfError, match="выходит за границы"):
        _overlay(_pdf(), _png(), _png(), _placement(signature_x_mm=205))


def test_overlay_rejects_missing_page():
    with pytest.raises(FacsimilePdfError, match="страница"):
        _overlay(_pdf(), _png(), _png(), _placement(page_number=2))
