from functools import partial

from modules.documents.infrastructure.renderers import TableBlockSpec
from modules.documents.infrastructure.renderers import sale_templates as source
from .initial_templates import ensure_initial_template
from .template_versions import NativeTemplatePlaceholderContract


async def ensure_sale_template(session, *, scope, selection, storage):
    document_type = selection.document_type
    receipt = document_type == "retail_receipt"
    extra_flags = {"receipt.has_note"} if receipt else {"equipment.has_serial", "certificate.has_components", "certificate.has_terms"}
    fields = source.COMMON_FIELDS | (source.RECEIPT_FIELDS if receipt else source.CERTIFICATE_FIELDS)
    blocks = (TableBlockSpec(name="lines", row_fields=frozenset(col[1] for col in source.RECEIPT_COLUMNS)),) if receipt else ()
    await ensure_initial_template(
        session, scope=scope, legal_entity_id=selection.legal_entity_id, storage=storage, document_type=document_type,
        name=source.FORM_TITLES[document_type] + " · редактируемая форма v1", filename=document_type + "-v1.docx",
        description=source.FORM_TITLES[document_type], content_factory=partial(source.template_bytes, document_type),
        placeholder_contract=NativeTemplatePlaceholderContract.create(
            field_catalog=fields, condition_catalog=source.COMMON_FLAGS | extra_flags, table_blocks=blocks,
        ),
    )
