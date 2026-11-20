"""Prepare scoped native inspection and defect acts for an existing order."""

from functools import partial

from sqlalchemy.ext.asyncio import AsyncSession

from core.command_actor import CommandActor
from core.config import settings
from crud import order_inspection
from modules.documents.infrastructure.renderers import TableBlockSpec
from modules.documents.infrastructure.renderers.order_technical_act_template import FIELDS, ROW_FIELDS, TITLES, template_bytes
from modules.documents.infrastructure.template_source_storage import TemplateSourceStorage
from schemas_order_diagnostics import OrderTechnicalActPrepared, PrepareOrderTechnicalActInput
from services.authenticated_command_service import AuthenticatedCommandService
from services.order_inspection_service import OrderInspectionConflict, inspection_item, resolve_inspection_scope
from services.public_write_idempotency_service import PublicWriteCommandResponse

from .context_builder import DocumentContextSelection
from .draft_parameters import draft_revision
from .errors import ManagedDocumentConflictError, ManagedDocumentNotFoundError
from .initial_templates import ensure_initial_template
from .lifecycle_service import ManagedDocumentService
from .order_technical_act_snapshot import OrderTechnicalActScope
from .template_versions import NativeTemplatePlaceholderContract


class OrderTechnicalActService:
    @staticmethod
    async def prepare(
        session: AsyncSession, actor: CommandActor, data: PrepareOrderTechnicalActInput, *,
        template_storage: TemplateSourceStorage,
    ):
        equipment_ids = [item.equipment_id for item in data.inspections]
        await resolve_inspection_scope(session, actor.tenant_scope, data.order_id, data.site_id, equipment_ids)

        async def create_draft() -> PublicWriteCommandResponse[OrderTechnicalActPrepared]:
            site, equipment = await resolve_inspection_scope(
                session, actor.tenant_scope, data.order_id, data.site_id, equipment_ids, write=True,
            )
            if site.version != data.expected_site_version:
                raise OrderInspectionConflict("Объект заказа изменён. Перечитайте его актуальную версию.")
            rows = await order_inspection.latest_inspections(
                session, order_id=data.order_id, site_id=data.site_id, equipment_ids=equipment_ids,
            )
            if any(rows.get(item.equipment_id) is None or rows[item.equipment_id].version != item.expected_version
                   for item in data.inspections):
                raise OrderInspectionConflict("Не найден осмотр выбранной версии. Перечитайте актуальные осмотры.")
            if data.document_type == "defect_act" and not any(row.facts["status"] == "defect_found" for row in rows.values()):
                raise ValueError("Для дефектного акта выберите оборудование с зафиксированным дефектом")
            if data.replaces_document_id is not None:
                source = await ManagedDocumentService.get_document(
                    session, tenant_scope=actor.tenant_scope, document_id=data.replaces_document_id,
                )
                if source.order_id != data.order_id:
                    raise ManagedDocumentNotFoundError("Заменяемый документ не найден")
                if (source.scope_meta or {}).get("site_id") != site.id:
                    raise ManagedDocumentConflictError("Исправление должно относиться к тому же объекту")

            by_equipment = {item.equipment_id: item for item in equipment}
            scope = OrderTechnicalActScope(
                site=site, equipment=tuple(by_equipment[equipment_id] for equipment_id in equipment_ids),
                inspections={equipment_id: inspection_item(row) for equipment_id, row in rows.items()},
                prepared_by_staff_id=actor.staff_user_id, prepared_by=actor.username,
            )
            if data.template_id is None:
                await ensure_initial_template(
                    session, scope=actor.tenant_scope, legal_entity_id=data.legal_entity_id, storage=template_storage,
                    document_type=data.document_type, name=TITLES[data.document_type],
                    filename=f"{data.document_type}-v1.docx", description="Фактические результаты осмотра оборудования объекта.",
                    content_factory=partial(template_bytes, data.document_type),
                    placeholder_contract=NativeTemplatePlaceholderContract.create(
                        field_catalog=FIELDS,
                        table_blocks=(TableBlockSpec(name="inspections", row_fields=ROW_FIELDS),),
                    ),
                )
            document = await ManagedDocumentService.create_draft(
                session, tenant_scope=actor.tenant_scope, selection=DocumentContextSelection(
                    order_id=data.order_id, document_type=data.document_type, legal_entity_id=data.legal_entity_id,
                    issue_date=data.issue_date, base_document_id=data.base_document_id,
                    base_customer_contract_id=data.base_customer_contract_id,
                    scope_customer_branch_id=site.customer_branch_id, scope_title=site.title, scope_address=site.address,
                    technical_act_scope=scope,
                ),
                template_id=data.template_id, replaces_document_id=data.replaces_document_id,
                template_storage=template_storage, commit=False,
            )
            result = OrderTechnicalActPrepared(
                order_id=data.order_id, site_id=data.site_id, equipment_ids=equipment_ids,
                document_id=document.id, document_type=data.document_type, status=document.status,
                revision=draft_revision(document),
                manager_url=f"{settings.MANAGER_BASE_URL.rstrip('/')}/orders/{data.order_id}?section=documents&documentId={document.id}",
            )
            return PublicWriteCommandResponse(result, resource_type="order_document", resource_id=document.id)

        outcome = await AuthenticatedCommandService.execute(
            session, actor=actor, command_name="order_technical_act.prepare", idempotency_key=data.idempotency_key,
            payload=data.model_dump(mode="json", exclude={"idempotency_key"}),
            response_model=OrderTechnicalActPrepared, operation=create_draft,
        )
        if outcome.replayed:
            await ManagedDocumentService.get_document(
                session, tenant_scope=actor.tenant_scope, document_id=outcome.value.document_id,
            )
        return outcome
