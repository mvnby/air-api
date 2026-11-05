"""First-use compact customer repair defect act."""
from modules.documents.infrastructure.renderers.repair_defect_template import CONDITIONS, FIELDS, NAME, TYPE, template_bytes
from .initial_templates import ensure_initial_template
from .template_versions import NativeTemplatePlaceholderContract


async def ensure_repair_defect_template(session, *, scope, legal_entity_id, storage):
    await ensure_initial_template(
        session, scope=scope, legal_entity_id=legal_entity_id, storage=storage,
        document_type=TYPE, name=NAME, filename="repair-defect-act-v1.docx",
        description="Заключение о ремонтопригодности, рекомендуемые действия, стоимость и срок.",
        content_factory=template_bytes,
        placeholder_contract=NativeTemplatePlaceholderContract.create(field_catalog=FIELDS, condition_catalog=CONDITIONS),
    )
