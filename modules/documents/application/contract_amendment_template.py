from modules.documents.infrastructure.renderers.contract_amendment_template import (
    NAME,
    FIELDS,
    TABLES,
    FLAGS,
    template_bytes,
)
from .initial_templates import ensure_initial_template
from .template_versions import NativeTemplatePlaceholderContract


async def ensure_amendment_template(session, *, scope, legal_entity_id, storage):
    await ensure_initial_template(
        session,
        scope=scope,
        legal_entity_id=legal_entity_id,
        storage=storage,
        document_type="contract_amendment",
        name=NAME,
        filename="contract-amendment-v1.docx",
        description="Дополнительные работы к зафиксированному договору. Проверьте оборудование, приёмку, оплату и вступление в силу.",
        content_factory=template_bytes,
        placeholder_contract=NativeTemplatePlaceholderContract.create(
            field_catalog=FIELDS, table_blocks=TABLES, condition_catalog=FLAGS
        ),
    )
