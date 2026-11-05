"""Editable native source forms for the customer's copy of a sale or warranty."""
from io import BytesIO

from docx import Document
from docx.oxml import OxmlElement
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt, RGBColor


FORM_TITLES = {"retail_receipt": "Товарный чек", "warranty_certificate": "Гарантийный талон"}
COMMON_FIELDS = {
    "document.official_full_number", "document.issued_on", "order.id", "customer.full_name",
    "seller.legal_name", "offer.url", "offer.version", "offer.published_on", "order.object_address",
}
COMMON_FLAGS = {"sale.has_offer", "order.has_object_address"}
RECEIPT_FIELDS = {"totals.amount", "receipt.note"}
CERTIFICATE_FIELDS = {
    "equipment.display_name", "equipment.serial", "certificate.components",
    "certificate.started_on", "certificate.expires_on", "warranty.goods.terms",
}
RECEIPT_COLUMNS = (
    ("Товар или работа", "line.title", 8.0), ("Кол-во", "line.quantity", 2.0),
    ("Цена, BYN", "line.unit_price", 3.4), ("Сумма, BYN", "line.amount", 3.6),
)


def _optional(document, flag, text):
    document.add_paragraph("{{#if " + flag + "}}")
    document.add_paragraph(text)
    document.add_paragraph("{{/if " + flag + "}}")


def template_bytes(document_type):
    document = Document()
    document.core_properties.author = ""
    section = document.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.left_margin = section.right_margin = Cm(2)
    section.top_margin = section.bottom_margin = Cm(2)
    normal = document.styles["Normal"]
    normal.font.name, normal.font.size = "DejaVu Sans", Pt(11)
    normal.font.color.rgb = RGBColor.from_string("17212B")
    normal.paragraph_format.space_after = Pt(6)
    title = document.styles["Title"]
    title.font.name, title.font.size = "DejaVu Sans", Pt(19)
    title.font.bold, title.font.color.rgb = True, RGBColor.from_string("17212B")
    for border in title.element.xpath(".//w:pBdr"):
        border.getparent().remove(border)
    document.add_paragraph(FORM_TITLES[document_type], style="Title")
    document.add_paragraph("№ {{ document.official_full_number }} от {{ document.issued_on }}")
    document.add_paragraph("Продавец: {{ seller.legal_name }}\nПокупатель: {{ customer.full_name }}")
    document.add_paragraph("Заказ № {{ order.id }}")
    _optional(document, "sale.has_offer", "Публичная оферта: {{ offer.url }}, редакция {{ offer.version }} от {{ offer.published_on }}")
    _optional(document, "order.has_object_address", "Объект: {{ order.object_address }}")
    if document_type == "retail_receipt":
        table = document.add_table(rows=2, cols=len(RECEIPT_COLUMNS))
        table.style = "Table Grid"
        table.autofit = False
        table.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
        for index, (label, field, width) in enumerate(RECEIPT_COLUMNS):
            table.columns[index].width = Cm(width)
            header, row = (table.cell(i, index) for i in range(2))
            header.width = row.width = Cm(width)
            header.paragraphs[0].add_run(label).bold = True
            row.text = ("{{ lines }}" if index == 0 else "") + "{{ " + field + " }}"
            for cell in (header, row):
                paragraph = cell.paragraphs[0]
                paragraph.paragraph_format.space_after = Pt(3)
                if index:
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        total = document.add_paragraph()
        total.paragraph_format.space_before = Pt(8)
        total.add_run("Итого: {{ totals.amount }} BYN").bold = True
        _optional(document, "receipt.has_note", "{{ receipt.note }}")
    else:
        document.add_paragraph("Оборудование: {{ equipment.display_name }}")
        _optional(document, "equipment.has_serial", "Серийный номер: {{ equipment.serial }}")
        _optional(document, "certificate.has_components", "Состав оборудования\n{{ certificate.components }}")
        document.add_paragraph("Срок гарантии: с {{ certificate.started_on }} по {{ certificate.expires_on }}")
        _optional(document, "certificate.has_terms", "{{ warranty.goods.terms }}")
    signatures = document.add_paragraph("Продавец __________________       Покупатель __________________")
    signatures.paragraph_format.space_before = Pt(16)
    output = BytesIO()
    document.save(output)
    return output.getvalue()
