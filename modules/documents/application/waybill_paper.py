"""A no-VAT paper form cannot establish the amounts for a VAT-paying seller."""

import asyncio
from datetime import datetime
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from .errors import ManagedDocumentConflictError, ManagedDocumentGenerationError
from modules.documents.infrastructure.renderers.pdf import PdfConversionError

EXEMPT_TOTAL = "waybill.no_vat_total"


def check_waybill_tax_profile(snapshot, schema, document_type):
    if document_type in {"tn2", "ttn1"} and EXEMPT_TOTAL in (schema or {}).get("fields", ()):
        if snapshot.get("conditions", {}).get("seller.is_not_vat_payer") is not True:
            raise ManagedDocumentConflictError(
                "Для продавца с НДС выберите шаблон накладной с расчётом НДС"
            )


def project_paper_waybill_values(values, fields):
    """The narrow operation boxes on paper show date and time on separate lines."""
    for stage in ("loading", "unloading"):
        for event in ("arrived_at", "departed_at"):
            field = f"waybill.{stage}.{event}"
            if field not in fields:
                continue
            stamp = values.get(f"transport.{stage}.{event}")
            values[field] = (
                datetime.strptime(stamp, "%d.%m.%Y %H:%M").strftime("%d.%m.%y %H:%M") if stamp else ""
            )


async def prepare_stock_files(
    *,
    document,
    template,
    version,
    issued_on,
    editable_source,
    required_placeholder_counts,
    template_storage,
    pdf_converter,
):
    schema = version.placeholder_schema or {}
    fields = set(schema.get("fields") or ())
    if document.doc_type not in {"tn2", "ttn1"} or "waybill.preprinted_a4" not in fields:
        return None
    from .editable_draft import DEFERRED_OFFICIAL_FIELDS
    from .issuance_artifacts import render_issued_files
    from .waybill_cargo import draft_snapshot_copy

    # The serial is already on the physical stock. With no numbering token in
    # the source these bytes are definitive before the sequence is advanced.
    if fields & (DEFERRED_OFFICIAL_FIELDS - {"document.issued_on"}):
        raise ManagedDocumentConflictError(
            "Форма для готового бланка содержит номер CRM. Уберите этот маркер либо выберите другой шаблон"
        )
    snapshot = draft_snapshot_copy(document.render_snapshot)
    values = snapshot["values"]
    values["document.issued_on"] = issued_on.strftime("%d.%m.%Y")
    try:
        files = await render_issued_files(
            tenant_id=document.tenant_id,
            document_type=document.doc_type,
            template=template,
            version=version,
            snapshot=snapshot,
            official_values=values,
            contract_act_number=None,
            editable_source=editable_source,
            required_placeholder_counts=required_placeholder_counts,
            template_storage=template_storage,
            pdf_converter=pdf_converter,
            basename="waybill",
        )
    except (PdfConversionError, OSError) as exc:
        raise ManagedDocumentGenerationError(
            "Не удалось подготовить PDF для проверки размера бланка; повторите выпуск"
        ) from exc
    await asyncio.to_thread(validate_stock_pdf, files[1])
    return files


def validate_stock_pdf(content: bytes):
    try:
        reader = PdfReader(BytesIO(content))
        pages = len(reader.pages)
        if pages == 1:
            page = reader.pages[0]
            dimensions = []
            for box in (page.mediabox, page.cropbox):
                mm_per_unit = float(page.user_unit) * 25.4 / 72
                width, height = float(box.width) * mm_per_unit, float(box.height) * mm_per_unit
                dimensions.append((height, width) if page.rotation % 180 else (width, height))
    except (PyPdfError, OSError, IndexError, TypeError, ValueError) as exc:
        raise ManagedDocumentConflictError(
            "Не удалось проверить размер страницы PDF перед выпуском бланка"
        ) from exc
    if pages != 1:
        raise ManagedDocumentConflictError(
            f"Накладная занимает {pages} стр. Для этого бланка нужна одна страница A4. "
            "Проверьте полный PDF, измените вёрстку или выберите другой шаблон для продолжения"
        )
    if any(abs(width - 210) > 1 or abs(height - 297) > 1 for width, height in dimensions):
        raise ManagedDocumentConflictError("Для печати на этом бланке установите книжную страницу A4")
