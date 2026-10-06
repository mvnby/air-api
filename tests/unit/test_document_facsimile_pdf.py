from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import RectangleObject
from reportlab.pdfgen.canvas import Canvas

from modules.documents.application.facsimile_pdf import FacsimilePdfError, _overlay
from modules.documents.application.facsimile_preview import page_dimensions, single_page_pdf, fit_initial_placement
from modules.documents.domain.facsimiles import FacsimileImagePlacement, FacsimilePlacement


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


def _two_pages(*, rotate=0, crop=False):
    writer = PdfWriter()
    for _ in range(2):
        page = PdfReader(BytesIO(_pdf())).pages[0]
        if crop:
            page.cropbox = RectangleObject([30, 40, 565, 800])
        if rotate:
            page.rotate(rotate)
        writer.add_page(page)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_images_can_be_placed_on_different_pages():
    original = _two_pages()
    positions = FacsimilePlacement(
        signature=FacsimileImagePlacement(page_number=1, x_mm=20, y_mm=30, width_mm=40),
        seal=FacsimileImagePlacement(page_number=2, x_mm=80, y_mm=60, width_mm=35),
    )
    result = PdfReader(BytesIO(_overlay(original, _png(), _png(), positions)))
    assert len(result.pages[0].images) == 1
    assert len(result.pages[1].images) == 1
    assert 'Original document' in result.pages[0].extract_text()
    assert 'Original document' in result.pages[1].extract_text()
    assert len(PdfReader(BytesIO(original)).pages[0].images) == 0


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_preview_and_saved_copy_share_display_geometry(rotation):
    original = _two_pages(rotate=rotation, crop=True)
    dimensions = page_dimensions(original)
    signed = _overlay(original, _png(), _png(), _placement())
    for saved, original_dimension in zip(page_dimensions(signed), dimensions):
        assert saved == pytest.approx(original_dimension)
    one_page = PdfReader(BytesIO(single_page_pdf(original, 2))).pages[0]
    saved_page = PdfReader(BytesIO(signed)).pages[0]
    assert one_page.rotation == saved_page.rotation == 0
    assert tuple(one_page.cropbox) == pytest.approx(tuple(saved_page.cropbox))
    expected_width, expected_height = ((760, 535) if rotation in {90, 270} else (535, 760))
    assert dimensions[0]['width_mm'] == pytest.approx(expected_width * 25.4 / 72)
    assert dimensions[0]['height_mm'] == pytest.approx(expected_height * 25.4 / 72)


def test_missing_defaults_start_on_last_page_and_fit_png_aspect_ratio():
    pages = [{'page_number': 1, 'width_mm': 210, 'height_mm': 297},
             {'page_number': 2, 'width_mm': 100, 'height_mm': 50}]
    assets = {kind: {'width_px': 100, 'height_px': 300} for kind in ('signature', 'seal')}
    placement = fit_initial_placement(None, pages, assets)
    for position in (placement.signature, placement.seal):
        assert position.page_number == 2
        assert position.x_mm + position.width_mm <= 100
        assert position.y_mm + position.width_mm * 3 <= 50


def test_invalid_or_encrypted_pdf_does_not_produce_preview():
    with pytest.raises(FacsimilePdfError, match='корректный'):
        page_dimensions(b'not a PDF')
    writer = PdfWriter()
    writer.add_page(PdfReader(BytesIO(_pdf())).pages[0])
    writer.encrypt('secret')
    output = BytesIO()
    writer.write(output)
    with pytest.raises(FacsimilePdfError, match='незашифрованный'):
        page_dimensions(output.getvalue())
