from email.message import EmailMessage
from types import SimpleNamespace

from PIL import Image

from services.mail_imap_service import MailImapService


def test_email_pdf_keeps_readable_pages_and_ocr_recovers_damaged_pages(monkeypatch):
    page_texts = [
        "Можно отремонтировать кондиционер?",
        "??????????? ?????? ?? ??????? № 12",
        "",
        "Результаты диагностики",
        "���������� � �����������",
        "?????? ?????? ??????",
        "???? ??????",
        "Подпись заказчика",
        "За пределами лимита текстовых страниц",
    ]
    monkeypatch.setattr("pypdf.PdfReader", lambda _: SimpleNamespace(pages=[
        SimpleNamespace(extract_text=lambda text=text: text) for text in page_texts
    ]))
    recognized = {
        2: "Просим сообщить стоимость ремонта",
        3: "Срок ответа 30 ноября",
        5: "Один наружный блок",
        6: "???? ????????",
    }
    rendered = []

    def render(content, *, first_page, last_page, dpi, timeout):
        assert content == b"mixed-pdf"
        assert first_page == last_page
        assert dpi == 200
        assert timeout > 0
        rendered.append(first_page)
        return [Image.new("L", (1, 1), color=first_page)]

    def ocr(image, *, lang, timeout):
        assert lang == "rus+eng"
        assert timeout > 0
        return recognized[image.getpixel((0, 0))]

    monkeypatch.setattr("pdf2image.convert_from_bytes", render)
    monkeypatch.setattr("pytesseract.image_to_string", ocr)
    message = EmailMessage()
    message.set_content("")
    message.add_attachment(b"mixed-pdf", maintype="application", subtype="pdf", filename="Заявка.pdf")

    assert MailImapService._extract_attachment_texts(message) == [
        "Вложение Заявка.pdf:\nМожно отремонтировать кондиционер? "
        "Просим сообщить стоимость ремонта Срок ответа 30 ноября "
        "Результаты диагностики Один наружный блок Подпись заказчика"
    ]
    assert rendered == [2, 3, 5, 6]
    assert MailImapService._extract_original_attachments(message)[0].content == b"mixed-pdf"


def test_email_pdf_without_readable_text_keeps_the_original_attachment(monkeypatch):
    page = SimpleNamespace(extract_text=lambda: "???? ????? ??????")
    monkeypatch.setattr("pypdf.PdfReader", lambda _: SimpleNamespace(pages=[page]))

    def render(*args, **kwargs):
        raise RuntimeError("PDF render deadline exceeded")

    monkeypatch.setattr("pdf2image.convert_from_bytes", render)
    message = EmailMessage()
    message.set_content("Просим предоставить предложение.")
    message.add_attachment(b"unreadable-pdf", maintype="application", subtype="pdf", filename="Акт.pdf")

    assert MailImapService._extract_attachment_texts(message) == [
        "Вложение Акт.pdf: текст не извлечен"
    ]
    assert MailImapService._extract_original_attachments(message)[0].content == b"unreadable-pdf"
