"""Native editable additional-work form; no customer-specific clauses or data."""

from datetime import datetime
from io import BytesIO
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.oxml import OxmlElement
from .contracts import TableBlockSpec

NAME = "Дополнительное соглашение · дополнительные работы v1"
FIELDS = frozenset(
    {
        "document.official_full_number",
        "document.issued_on",
        "document.issue_city",
        "basis.number",
        "basis.date",
        "seller.legal_name",
        "seller.unp",
        "seller.legal_address",
        "seller.bank_name",
        "seller.iban",
        "seller.bic",
        "seller.signer_position",
        "seller.signer_name",
        "seller.acting_basis",
        "customer.full_name",
        "customer.unp",
        "customer.legal_address",
        "customer.bank_name",
        "customer.iban",
        "customer.bic",
        "customer.signer_position",
        "customer.signer_name",
        "customer.acting_basis",
        "totals.amount",
        "totals.currency",
        "totals.vat_label",
        *(
            f"amendment.{key}"
            for key in (
                "equipment",
                "original_amount",
                "other_amount",
                "previous_total",
                "new_total",
                "acceptance_terms",
                "payment_terms",
                "effective_terms",
            )
        ),
    }
)
FLAGS = frozenset(
    f"{party}.{key}"
    for party in ("seller", "customer")
    for key in (
        "is_organization",
        "is_individual_entrepreneur",
        "signs_self",
        "signs_as_statutory_body",
        "signs_by_power_of_attorney",
    )
)


def optional(doc, flag, text):
    doc.add_paragraph("{{#if " + flag + "}}")
    doc.add_paragraph(text)
    doc.add_paragraph("{{/if " + flag + "}}")


def party_details(doc, prefix, label, name_field):
    doc.add_paragraph(label + ": {{ " + prefix + "." + name_field + " }}")
    doc.add_paragraph("Адрес: {{ " + prefix + ".legal_address }}")
    bank = (
        "УНП: {{ "
        + prefix
        + ".unp }}. {{ "
        + prefix
        + ".bank_name }}, {{ "
        + prefix
        + ".iban }}, БИК {{ "
        + prefix
        + ".bic }}"
    )
    for key in ("is_organization", "is_individual_entrepreneur"):
        optional(doc, prefix + "." + key, bank)
    optional(
        doc,
        prefix + ".signs_self",
        "{{ " + prefix + "." + name_field + " }} ____________________",
    )
    for key in ("signs_as_statutory_body", "signs_by_power_of_attorney"):
        optional(
            doc,
            prefix + "." + key,
            "{{ "
            + prefix
            + ".signer_position }} {{ "
            + prefix
            + ".signer_name }} ____________________",
        )


TABLES = (
    TableBlockSpec(
        "lines",
        frozenset(
            {
                "line.number",
                "line.title",
                "line.quantity",
                "line.unit",
                "line.unit_price",
                "line.amount",
            }
        ),
    ),
)


def template_bytes():
    doc = Document()
    doc.core_properties.author = ""
    doc.core_properties.created = doc.core_properties.modified = datetime(2026, 11, 10)
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin = section.bottom_margin = Cm(1.7)
    section.left_margin = section.right_margin = Cm(1.8)
    for name in ("Normal", "Title", "Heading 1"):
        doc.styles[name].font.name = "DejaVu Sans"
        doc.styles[name].font.color.rgb = RGBColor(0, 0, 0)
    doc.styles["Normal"].font.size = Pt(10.5)
    doc.styles["Normal"].paragraph_format.space_after = Pt(6)
    doc.styles["Title"].font.size = Pt(15)
    for border in doc.styles["Title"].element.xpath(".//w:pBdr"):
        border.getparent().remove(border)
    doc.styles["Heading 1"].font.size = Pt(11)
    doc.add_paragraph(
        "Дополнительное соглашение № {{ document.official_full_number }}", "Title"
    )
    doc.add_paragraph("к договору № {{ basis.number }} от {{ basis.date }}")
    doc.add_paragraph(
        "{{ document.issue_city }}                                      {{ document.issued_on }}"
    )
    doc.add_paragraph(
        "{{ seller.legal_name }} и {{ customer.full_name }}, совместно именуемые «Стороны», согласовали следующее."
    )
    for prefix, label in (("seller", "Наша сторона"), ("customer", "Клиент")):
        optional(
            doc, prefix + ".signs_self", label + " действует от собственного имени."
        )
        for key in ("signs_as_statutory_body", "signs_by_power_of_attorney"):
            optional(
                doc,
                prefix + "." + key,
                label
                + ": представитель {{ "
                + prefix
                + ".signer_position }} {{ "
                + prefix
                + ".signer_name }}, основание полномочий: {{ "
                + prefix
                + ".acting_basis }}.",
            )
    doc.add_paragraph("1. Дополнительный объём", "Heading 1")
    doc.add_paragraph(
        "К составу исходного договора добавляются только перечисленные ниже работы. Оборудование / объект: {{ amendment.equipment }}"
    )
    table = doc.add_table(rows=1, cols=6)
    table.style = "Table Grid"
    table.autofit = False
    widths = (0.7, 6.9, 1.9, 2.1, 2.9, 2.9)
    for col, width in zip(table.columns, widths):
        col.width = Cm(width)
    for cell, label in zip(
        table.rows[0].cells,
        ("№", "Дополнительные работы", "Кол-во", "Ед.", "Цена, BYN", "Сумма, BYN"),
    ):
        cell.text = label
    header = OxmlElement("w:tblHeader")
    table.rows[0]._tr.get_or_add_trPr().append(header)
    row = table.add_row()
    for cell, field in zip(
        row.cells,
        (
            "line.number",
            "line.title",
            "line.quantity",
            "line.unit",
            "line.unit_price",
            "line.amount",
        ),
    ):
        cell.text = (
            ("{{ lines }} " if field == "line.number" else "") + "{{ " + field + " }}"
        )
    doc.add_paragraph(
        "Стоимость дополнительных работ: {{ totals.amount }} {{ totals.currency }}, {{ totals.vat_label }}."
    )
    doc.paragraphs[-1].paragraph_format.space_before = Pt(6)
    doc.add_paragraph("2. Изменение суммы договора", "Heading 1")
    doc.add_paragraph(
        "Первоначальная сумма: {{ amendment.original_amount }} BYN. Другие действующие изменения: {{ amendment.other_amount }} BYN. Сумма без настоящего соглашения: {{ amendment.previous_total }} BYN. С учётом настоящего соглашения общая сумма договора составляет {{ amendment.new_total }} BYN."
    )
    doc.add_paragraph("3. Сдача, приёмка, оплата и вступление в силу", "Heading 1")
    for key in ("acceptance_terms", "payment_terms", "effective_terms"):
        doc.add_paragraph("{{ amendment." + key + " }}")
    doc.add_paragraph(
        "Остальные условия исходного договора сохраняются. Настоящее соглашение является его неотъемлемой частью. Документ сам по себе не подтверждает выполнение работ или оплату."
    )
    doc.add_paragraph("4. Реквизиты и подписи сторон", "Heading 1")
    party_details(doc, "seller", "Наша сторона", "legal_name")
    party_details(doc, "customer", "Клиент", "full_name")
    # Prevent Word from dividing a work row over pages.
    for row in table.rows:
        row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
    out = BytesIO()
    doc.save(out)
    return out.getvalue()
