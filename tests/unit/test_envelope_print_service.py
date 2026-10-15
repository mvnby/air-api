from io import BytesIO
import base64

import pytest
from pydantic import ValidationError
from pypdf import PdfReader
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from PIL import Image

from services.envelope_print_service import EnvelopeBranding, EnvelopeParty, EnvelopePrintPayload, render_envelope_pdf
from services.envelope_print_service import _font_name


def payload(**recipient_changes):
    return EnvelopePrintPayload(
        sender=EnvelopeParty(name='ООО «Отправитель»', address='г. Минск, ул. Ленина, д. 1', postal_code='220030'),
        recipient=EnvelopeParty(**{
            'name': 'Учреждение здравоохранения «Областной клинический центр»',
            'address': 'Витебская область, г. Витебск, ул. Доватора, д. 2, каб. 12',
            'postal_code': '210001', **recipient_changes,
        }),
    )


def test_dl_dimensions_cyrillic_and_embedded_font():
    reader = PdfReader(BytesIO(render_envelope_pdf(payload())))
    assert len(reader.pages) == 1
    page = reader.pages[0]
    assert float(page.mediabox.width) == pytest.approx(220 * mm, abs=.001)
    assert float(page.mediabox.height) == pytest.approx(110 * mm, abs=.001)
    text = page.extract_text()
    assert 'ООО «Отправитель»' in text
    assert 'Областной клинический центр' in text.replace('\n', ' ')
    assert '220030' in text and '210001' in text
    assert any(font.get_object().get('/FontDescriptor', {}).get('/FontFile2')
               for font in page['/Resources']['/Font'].values())


@pytest.mark.parametrize('changes', [
    {'postal_code': ''}, {'postal_code': '22003'}, {'postal_code': '2200300'},
    {'postal_code': '２２００３０'}, {'name': '   '}, {'address': '\n '}, {'name': 'Имя\x00'},
])
def test_missing_or_invalid_address_data_is_rejected(changes):
    with pytest.raises(ValidationError):
        payload(**changes)


def test_plain_text_is_not_interpreted_as_pdf_markup():
    text = PdfReader(BytesIO(render_envelope_pdf(payload(name='ООО <Тест & Ко>')))).pages[0].extract_text()
    assert 'ООО <Тест & Ко>' in text


def test_excessive_text_is_reported_instead_of_clipped():
    with pytest.raises(ValueError, match='не помещается'):
        render_envelope_pdf(payload(name='Ш' * 300, address='Ш' * 600))


def test_unknown_envelope_format_is_rejected():
    data = payload().model_dump()
    data['format'] = 'C3'
    with pytest.raises(ValidationError):
        EnvelopePrintPayload.model_validate(data)


@pytest.mark.parametrize('code,width,height', [
    ('DL', 220, 110), ('C6', 162, 114), ('C5', 229, 162), ('C4', 324, 229),
])
def test_formats_print_at_actual_size_with_readable_addresses_and_branding(code, width, height):
    data = payload(
        name='Общество с ограниченной ответственностью «Строй Тайм Компани»',
        address='Минская область, Минский район, д. Боровляны, ул. Центральная, д. 83, оф. 27',
        postal_code='223053',
    )
    data.format = code
    data.sender.name = 'Индивидуальный предприниматель Янчевич Дмитрий Викторович'
    data.branding = EnvelopeBranding(name='Наша организация', logo_data_url=logo_data())
    reader = PdfReader(BytesIO(render_envelope_pdf(data)))
    assert len(reader.pages) == 1
    page = reader.pages[0]
    assert float(page.mediabox.width) == pytest.approx(width * mm, abs=.001)
    assert float(page.mediabox.height) == pytest.approx(height * mm, abs=.001)
    assert reader.metadata.title == f'Конверт {code}'
    fragments = []
    text = page.extract_text(visitor_text=lambda text, cm, tm, font, size: fragments.append(
        (text.strip(), cm[4] + tm[4], cm[5] + tm[5], font, size)))
    for expected in ['Янчевич', 'Строй Тайм', '223053', 'Минский район', 'Минская область', 'Наша организация']:
        assert expected in text.replace('\n', ' ')
    assert len(page.images) == 1
    for content, x, y, font, size in fragments:
        if not content:
            continue
        text_width = pdfmetrics.stringWidth(content, _font_name('Bold' in str(font['/BaseFont'])), size)
        assert x >= 8 * mm - .01
        assert x + text_width <= (width - 8) * mm + .01
        assert size >= (7 if content in ('Отправитель', 'Получатель') else 8.5)
        # pypdf's visitor misplaces subsequent wrapped lines; use the standalone
        # postcode to check the recipient's physical position, and render for QA.
        if content == '223053':
            assert x == pytest.approx(width / 2 * mm, abs=.001)
            assert 14 * mm <= y <= (height - 35) * mm


def logo_data(size=(80, 30)):
    image = Image.new('RGB', size, 'blue')
    output = BytesIO()
    image.save(output, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(output.getvalue()).decode()


def test_postal_lines_bold_names_larger_index_and_lower_recipient():
    data = payload(name='ООО «Строй Тайм Компани»', address='д. Боровляны, Минская область, Минский район, д. 83, оф. 27', postal_code='223053')
    fragments = []
    page = PdfReader(BytesIO(render_envelope_pdf(data))).pages[0]
    text = page.extract_text(visitor_text=lambda text, cm, tm, font, size: fragments.append((text.strip(), cm[4] + tm[4], cm[5] + tm[5], font, size)))
    assert text.index('д. 83, оф. 27') < text.index('223053') < text.index('Минский район') < text.index('Минская область')
    name = next(item for item in fragments if 'Строй' in item[0])
    postcode = next(item for item in fragments if item[0] == '223053')
    street = next(item for item in fragments if 'д. 83' in item[0])
    assert 'Bold' in str(name[3]['/BaseFont'])
    assert 'Bold' in str(postcode[3]['/BaseFont'])
    assert postcode[4] > street[4]
    assert name[1] == pytest.approx(110 * mm, abs=.001)
    assert name[2] < 54 * mm
    assert not any(text and x > 170 * mm and y > 70 * mm for text, x, y, _, _ in fragments)


def test_optional_branding_is_bounded_to_lower_left():
    data = payload()
    data.branding = EnvelopeBranding(name='Наша организация', logo_data_url=logo_data())
    fragments = []
    page = PdfReader(BytesIO(render_envelope_pdf(data))).pages[0]
    page.extract_text(visitor_text=lambda text, cm, tm, font, size: fragments.append((text.strip(), cm[4] + tm[4], cm[5] + tm[5])))
    name = next(item for item in fragments if 'Наша организация' in item[0])
    assert name[1] < 90 * mm and 15 * mm <= name[2] <= 33 * mm
    assert len(page.images) == 1


@pytest.mark.parametrize('logo', ['data:image/png;base64,bm90LWFuLWltYWdl', logo_data((2001, 1))])
def test_corrupt_or_excessive_logo_is_rejected(logo):
    data = payload()
    data.branding = EnvelopeBranding(logo_data_url=logo)
    with pytest.raises(ValueError, match='логотип|Логотип'):
        render_envelope_pdf(data)


@pytest.mark.parametrize('logo', ['https://example.com/logo.png', 'data:image/svg+xml;base64,PHN2Zz4=', 'data:image/png;base64,' + 'A' * 350001])
def test_only_bounded_embedded_raster_logo_is_accepted(logo):
    with pytest.raises(ValidationError):
        EnvelopeBranding(logo_data_url=logo)


def test_conflicting_postcode_requires_correction_before_printing():
    with pytest.raises(ValueError, match='индекс в адресе отличается'):
        render_envelope_pdf(payload(address='220004, г. Минск, ул. Ленина, 1', postal_code='220030'))


def test_pasted_multiline_address_keeps_part_boundaries():
    text = PdfReader(BytesIO(render_envelope_pdf(payload(address='Витебская область\nг. Витебск\nул. Доватора\nд. 2')))).pages[0].extract_text()
    assert 'ул. Доватора, д. 2' in text
    assert text.index('210001') < text.index('Витебская область')
