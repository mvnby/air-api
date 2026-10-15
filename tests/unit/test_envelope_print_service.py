from io import BytesIO

import pytest
from pydantic import ValidationError
from pypdf import PdfReader
from reportlab.lib.units import mm

from services.envelope_print_service import EnvelopeParty, EnvelopePrintPayload, render_envelope_pdf


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
    data['format'] = 'C5'
    with pytest.raises(ValidationError):
        EnvelopePrintPayload.model_validate(data)
