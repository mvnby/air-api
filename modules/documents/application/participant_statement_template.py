"""First-use initial participant statement form."""
from modules.documents.infrastructure.renderers.participant_statement_template import TYPE, NAME, FIELDS, template_bytes
from .initial_templates import ensure_initial_template
from .template_versions import NativeTemplatePlaceholderContract


async def ensure_initial_participant_template(session, *, scope, legal_entity_id, storage):
    await ensure_initial_template(
        session, scope=scope, legal_entity_id=legal_entity_id, storage=storage,
        document_type=TYPE, name=NAME, filename="participant-statement-v1.docx",
        description="Редактируемая форма. Сверьте текст и факты с требованиями конкретной закупки перед выпуском.",
        allow_alongside_custom=True,
        content_factory=template_bytes, placeholder_contract=NativeTemplatePlaceholderContract.create(field_catalog=FIELDS),
    )
