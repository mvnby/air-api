"""Native first-use forms for service and repair inspection results."""

from datetime import datetime
from io import BytesIO

from docx import Document
from docx.shared import Cm, Pt

from modules.documents.domain.placeholder_catalog import ORDER_INSPECTION_ROW_PLACEHOLDERS


TITLES = {
    "technical_inspection_act": "Акт технического обследования",
    "defect_act": "Дефектный акт",
}
FIELDS = frozenset({
    "document.official_full_number", "document.issued_on", "seller.legal_name", "customer.full_name",
    "order.id", "order.object_title", "order.object_address", "basis.type", "basis.number", "basis.date",
})
ROW_FIELDS = frozenset(item.name for item in ORDER_INSPECTION_ROW_PLACEHOLDERS)


def template_bytes(document_type: str) -> bytes:
    document = Document()
    document.core_properties.author = ""
    document.core_properties.created = datetime(2026, 11, 20)
    document.core_properties.modified = document.core_properties.created
    section = document.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin = section.bottom_margin = section.left_margin = section.right_margin = Cm(2)
    document.styles["Normal"].font.name = "DejaVu Sans"
    document.styles["Normal"].font.size = Pt(10)
    document.add_heading(TITLES[document_type] + " № {{ document.official_full_number }}", 1)
    document.add_paragraph("Дата: {{ document.issued_on }}")
    document.add_paragraph("Исполнитель: {{ seller.legal_name }}")
    document.add_paragraph("Заказчик: {{ customer.full_name }}")
    document.add_paragraph("Объект: {{ order.object_title }}\nАдрес: {{ order.object_address }}")
    document.add_paragraph("Основание: {{ basis.type }} № {{ basis.number }} от {{ basis.date }}\nЗаказ № {{ order.id }}")
    table = document.add_table(rows=1, cols=1)
    table.style = "Table Grid"
    cell = table.cell(0, 0)
    cell.paragraphs[0].add_run("{{ inspections }}{{ inspection.equipment }}").bold = True
    for field in ORDER_INSPECTION_ROW_PLACEHOLDERS:
        if field.name == "inspection.equipment":
            continue
        paragraph = cell.add_paragraph()
        paragraph.add_run(field.label + ": ").bold = True
        paragraph.add_run("{{ " + field.name + " }}")
    document.add_paragraph("Исполнитель ______________________    Заказчик ______________________")
    output = BytesIO()
    document.save(output)
    return output.getvalue()
