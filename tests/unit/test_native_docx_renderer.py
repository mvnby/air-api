from io import BytesIO

import pytest
from docx import Document

from modules.documents.infrastructure.renderers import (
    ContextFieldError,
    DocumentTemplateVersion,
    GotenbergPdfConverter,
    NativeDocxRenderer,
    RenderContext,
    TableBlockSpec,
    TemplateValidationError,
    UnavailablePdfConverter,
)
from modules.documents.infrastructure.renderers.pdf import (
    PdfConversionError,
    PdfConversionUnavailableError,
)


def _template_bytes(*, unknown_placeholder: str | None = None) -> bytes:
    document = Document()
    heading = document.add_paragraph("Документ № ")
    heading.add_run("{{ document.")
    heading.add_run("official_number }}")
    document.add_paragraph("Клиент: {{ customer.full_name }}")
    if unknown_placeholder:
        document.add_paragraph(f"Скрытое: {{{{ {unknown_placeholder} }}}}")
    table = document.add_table(rows=1, cols=4)
    row = table.rows[0].cells
    row[0].text = "{{ lines }}{{ line.number }}"
    row[1].text = "{{ line.title }}"
    row[2].text = "{{ line.quantity }}"
    row[3].text = "{{ line.amount }}"
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _template(source: bytes) -> DocumentTemplateVersion:
    return DocumentTemplateVersion(
        template_key="invoice",
        version=3,
        source=source,
        field_catalog=frozenset({"document.official_number", "customer.full_name"}),
        table_blocks=(
            TableBlockSpec(
                name="lines",
                row_fields=frozenset(
                    {"line.number", "line.title", "line.quantity", "line.amount"}
                ),
            ),
        ),
    )


def test_native_renderer_replaces_split_placeholders_and_repeats_table_rows():
    rendered = NativeDocxRenderer().render(
        _template(_template_bytes()),
        RenderContext(
            values={
                "document.official_number": "С-2026-001",
                "customer.full_name": "ООО Тест",
            },
            table_rows={
                "lines": (
                    {
                        "line.number": "1",
                        "line.title": "Кондиционер",
                        "line.quantity": "1",
                        "line.amount": "2500.00",
                    },
                    {
                        "line.number": "2",
                        "line.title": "Монтаж",
                        "line.quantity": "1",
                        "line.amount": "500.00",
                    },
                )
            },
        ),
    )

    result = Document(BytesIO(rendered.content))
    assert [paragraph.text for paragraph in result.paragraphs] == [
        "Документ № С-2026-001",
        "Клиент: ООО Тест",
    ]
    assert [[cell.text for cell in row.cells] for row in result.tables[0].rows] == [
        ["1", "Кондиционер", "1", "2500.00"],
        ["2", "Монтаж", "1", "500.00"],
    ]
    assert rendered.template_key == "invoice"
    assert rendered.template_version == 3


def test_renderer_discovers_template_placeholders_without_expanding_catalogue():
    discovered = NativeDocxRenderer().discover_placeholders(_template_bytes())

    assert discovered == {
        "document.official_number",
        "customer.full_name",
        "lines",
        "line.number",
        "line.title",
        "line.quantity",
        "line.amount",
    }


def test_renderer_refuses_unapproved_context_fields_before_any_document_is_emitted():
    context = RenderContext(
        values={
            "document.official_number": "С-2026-001",
            "customer.full_name": "ООО Тест",
            "internal.audit_secret": "classified",
        },
        table_rows={"lines": ()},
    )

    with pytest.raises(ContextFieldError, match="internal.audit_secret"):
        NativeDocxRenderer().render(_template(_template_bytes()), context)


def test_render_context_is_frozen_after_the_document_snapshot_is_built():
    context = RenderContext(
        values={"document.official_number": "С-2026-001"},
        table_rows={"lines": ({"line.number": "1"},)},
    )

    with pytest.raises(TypeError):
        context.values["document.official_number"] = "С-2026-002"
    with pytest.raises(TypeError):
        context.table_rows["lines"][0]["line.number"] = "2"


def test_renderer_refuses_unknown_template_placeholder_without_leaking_context_data():
    context = RenderContext(
        values={
            "document.official_number": "С-2026-001",
            "customer.full_name": "ООО Тест",
        },
        table_rows={"lines": ()},
    )

    with pytest.raises(TemplateValidationError, match="internal.secret"):
        NativeDocxRenderer().render(
            _template(_template_bytes(unknown_placeholder="internal.secret")), context
        )


def test_unconfigured_pdf_converter_is_explicitly_unavailable():
    converter = UnavailablePdfConverter()

    assert converter.health().available is False
    with pytest.raises(
        PdfConversionUnavailableError, match="No PDF conversion provider"
    ):
        converter.convert_docx(b"not-a-real-docx")


def test_gotenberg_health_reports_an_unreachable_explicit_endpoint(monkeypatch):
    import httpx

    def _unreachable(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(
        "modules.documents.infrastructure.renderers.pdf.httpx.get", _unreachable
    )

    health = GotenbergPdfConverter("http://gotenberg.example.invalid").health()

    assert health.available is False
    assert health.provider == "gotenberg"
    assert "unreachable" in health.detail


def test_gotenberg_rejects_success_response_that_is_not_a_pdf(monkeypatch):
    import httpx

    request = httpx.Request("POST", "http://gotenberg.example.invalid")
    monkeypatch.setattr(
        "modules.documents.infrastructure.renderers.pdf.httpx.post",
        lambda *args, **kwargs: httpx.Response(
            200, content=b"<html>proxy error</html>", request=request
        ),
    )

    with pytest.raises(PdfConversionError, match="not a PDF"):
        GotenbergPdfConverter("http://gotenberg.example.invalid").convert_docx(
            b"PK-docx",
            filename="contract.docx",
        )
