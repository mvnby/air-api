"""A short, editable A4 repair expert opinion for the customer."""
from datetime import datetime
from io import BytesIO

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt, RGBColor

TYPE = "repair_defect_act"
NAME = "Дефектный акт ремонта · заключение для клиента"
FIELDS = frozenset({
    "document.official_full_number", "document.issued_on", "seller.legal_name", "customer.full_name",
    "order.object_address", "repair.equipment", "repair.verdict", "repair.finding",
    "repair.recommendation", "repair.restriction", "repair.cost", "repair.term", "repair.estimate_note",
})
CONDITIONS = frozenset({"order.has_object_address", "repair.has_restriction", "repair.has_cost", "repair.has_term", "repair.has_estimate_note"})


def template_bytes() -> bytes:
    doc = Document()
    doc.core_properties.author = ""
    doc.core_properties.title = "Дефектный акт"
    doc.core_properties.created = doc.core_properties.modified = datetime(2026, 11, 5)
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.left_margin = section.right_margin = Cm(2)
    section.top_margin = section.bottom_margin = Cm(1.9)
    normal = doc.styles["Normal"]
    normal.font.name = "DejaVu Sans"
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = RGBColor.from_string("161616")
    normal.paragraph_format.space_after = Pt(5)
    normal.paragraph_format.line_spacing = 1.12

    heading = doc.add_paragraph()
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title = heading.add_run("Дефектный акт № {{ document.official_full_number }}")
    title.bold, title.font.size = True, Pt(16)
    issued = doc.add_paragraph("{{ document.issued_on }}")
    issued.alignment = WD_ALIGN_PARAGRAPH.CENTER
    issued.paragraph_format.space_after = Pt(14)

    def line(label: str, placeholder: str, condition: str | None = None) -> None:
        if condition:
            doc.add_paragraph("{{#if " + condition + "}}")
        paragraph = doc.add_paragraph()
        paragraph.add_run(label + "  ").bold = True
        paragraph.add_run("{{ " + placeholder + " }}")
        if condition:
            doc.add_paragraph("{{/if " + condition + "}}")

    line("Исполнитель", "seller.legal_name")
    line("Заказчик", "customer.full_name")
    line("Объект", "order.object_address", "order.has_object_address")
    line("Оборудование", "repair.equipment")
    verdict = doc.add_paragraph()
    verdict.paragraph_format.space_before = Pt(10)
    verdict.paragraph_format.space_after = Pt(8)
    conclusion = verdict.add_run("{{ repair.verdict }}")
    conclusion.bold, conclusion.font.size = True, Pt(13)
    line("Установлено", "repair.finding")
    line("Рекомендуем", "repair.recommendation")
    line("Ограничение эксплуатации", "repair.restriction", "repair.has_restriction")
    doc.add_paragraph("{{#if repair.has_estimate_note}}")
    doc.add_paragraph("{{ repair.estimate_note }}")
    doc.add_paragraph("{{/if repair.has_estimate_note}}")
    line("Стоимость ремонта", "repair.cost", "repair.has_cost")
    line("Срок ремонта", "repair.term", "repair.has_term")

    signatures = doc.add_table(rows=1, cols=2)
    for cell, label in zip(signatures.rows[0].cells, ("Исполнитель", "Заказчик")):
        paragraph = cell.paragraphs[0]
        paragraph.paragraph_format.space_before = Pt(16)
        paragraph.add_run(label + " __________________")
    output = BytesIO()
    doc.save(output)
    return output.getvalue()
