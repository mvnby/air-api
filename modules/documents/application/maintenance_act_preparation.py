"""Explicit maintenance continuation command, independent of DocumentService."""
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from models.tenancy import TenantScope
from api_contracts.maintenance_observations import PrepareMaintenanceDefectAct
from modules.documents.infrastructure.template_source_storage import TemplateSourceStorage

from sqlmodel import select, func
from models import (Order, OrderStatus, Customer, CustomerBranch, DocumentLegalEntity, DocumentTemplate,
                    DocumentTemplateVersion, MaintenanceContinuation, MaintenanceActPreparation,
                    MaintenanceActSource, MaintenanceObservationRevision)
from services.maintenance_observation_service import MaintenanceObservationService as Observations, ObservationConflict, ObservationNotFound, command_hash
from services.command_transaction import command_transaction
from services.tenant_entity_access_service import TenantEntityAccessService as Access
from modules.documents.infrastructure.renderers import NativeDocxRenderer, DocumentTemplateVersion as RenderTemplate
from modules.documents.infrastructure.renderers.maintenance_act_template import TYPE, NAME, FIELDS, ROW_FIELDS, template_bytes
from .template_versions import NativeTemplatePlaceholderContract
from modules.documents.infrastructure.renderers import TableBlockSpec
from .context_builder import DocumentContextSelection
from .lifecycle_service import ManagedDocumentService


class MaintenanceActPreparationService:
    @staticmethod
    async def item(session, preparation, continuation, scope):
        document = await ManagedDocumentService.get_document(session, tenant_scope=scope, document_id=preparation.document_id)
        refs = (await session.execute(select(MaintenanceObservationRevision)
            .join(MaintenanceActSource, MaintenanceActSource.revision_id == MaintenanceObservationRevision.id)
            .where(MaintenanceActSource.preparation_id == preparation.id)
            .order_by(MaintenanceObservationRevision.observation_id))).scalars().all()
        return dict(preparation_id=preparation.id, source_order_id=continuation.source_order_id,
                    continuation_order_id=continuation.order_id, document_id=document.id, status=document.status,
                    observations=[dict(observation_id=r.observation_id, expected_version=r.version) for r in refs])

    @classmethod
    async def list(cls, session, *, source_order_id, scope, limit=50, offset=0):
        if not await Access.get_order(session, source_order_id, tenant_scope=scope):
            raise ObservationNotFound("Исходное ТО не найдено")
        continuation = await session.scalar(select(MaintenanceContinuation).where(MaintenanceContinuation.source_order_id == source_order_id))
        if continuation is None:
            return dict(items=[], total=0)
        await cls.validate_continuation(session, continuation, scope)
        query = select(MaintenanceActPreparation).where(MaintenanceActPreparation.continuation_id == continuation.id)
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        rows = (await session.execute(query.order_by(MaintenanceActPreparation.id.desc()).limit(limit).offset(offset))).scalars().all()
        return dict(items=[await cls.item(session, p, continuation, scope) for p in rows], total=total)

    @staticmethod
    async def validate_continuation(session, continuation, scope, *, lock=False):
        order = await Access.get_order(session, continuation.order_id, tenant_scope=scope, for_update=lock, populate_existing=True)
        if order is None:
            raise ObservationNotFound("Продолжение ТО не найдено")
        if (order.customer_id, order.customer_branch_id, order.tenant_id, order.storefront_id) != (continuation.customer_id, continuation.customer_branch_id, continuation.tenant_id, continuation.storefront_id):
            raise ObservationConflict("Контекст продолжения изменён")
        return order

    @staticmethod
    async def template(session, *, issuer, scope, storage):
        # Issuer row lock serializes first-use template setup across source orders.
        existing = await session.scalar(select(DocumentTemplate).where(DocumentTemplate.tenant_id == scope.tenant_id,
            DocumentTemplate.legal_entity_id == issuer.id, DocumentTemplate.name == NAME, DocumentTemplate.doc_type == TYPE))
        if existing:
            if not existing.is_active:
                raise ObservationConflict("Шаблон дефектного акта отключён. Уточните настройки документов.")
            return existing.id
        content = await asyncio.to_thread(template_bytes)
        contract = NativeTemplatePlaceholderContract.create(field_catalog=FIELDS,
            table_blocks=(TableBlockSpec(name="observations", row_fields=ROW_FIELDS),))
        render = RenderTemplate(template_key=TYPE, version=1, source=content, field_catalog=contract.field_catalog,
                                table_blocks=contract.table_blocks)
        validation = NativeDocxRenderer().validate(render)
        if not validation.is_valid:
            raise ValueError("Шаблон дефектного акта не прошёл проверку")
        template = DocumentTemplate(tenant_id=scope.tenant_id, legal_entity_id=issuer.id, name=NAME, doc_type=TYPE, is_default=True)
        session.add(template); await session.flush()
        source = await storage.save(tenant_id=scope.tenant_id, template_id=template.id, version=1,
                                    filename="maintenance-defect-act-v1.docx", content=content)
        version = DocumentTemplateVersion(template_id=template.id, version=1, status='active', renderer='docx',
                    source_storage_key=source.storage_key, source_filename=source.filename, checksum_sha256=source.checksum_sha256,
                    placeholder_schema=contract.as_persisted_schema(), change_note="Факты и рекомендации из выбранных замечаний ТО")
        session.add(version); await session.flush()
        return template.id

    @classmethod
    async def prepare(cls, session: AsyncSession, *, source_order_id: int, payload: PrepareMaintenanceDefectAct,
                      actor: str, scope: TenantScope, storage: TemplateSourceStorage):
        async with command_transaction(session):
            return await cls._prepare(session, source_order_id=source_order_id, payload=payload,
                                      actor=actor, scope=scope, storage=storage)

    @classmethod
    async def _prepare(cls, session, *, source_order_id, payload, actor, scope, storage):
        source = await Access.get_order(session, source_order_id, tenant_scope=scope, for_update=True, populate_existing=True)
        if source is None:
            raise ObservationNotFound("Исходное ТО не найдено")
        continuation = await session.scalar(select(MaintenanceContinuation).where(MaintenanceContinuation.source_order_id == source_order_id))
        digest = command_hash(payload.model_dump(mode='json', exclude={'command_key'}))
        if continuation:
            await cls.validate_continuation(session, continuation, scope, lock=True)
            previous = await session.scalar(select(MaintenanceActPreparation).where(
                MaintenanceActPreparation.continuation_id == continuation.id, MaintenanceActPreparation.command_key == str(payload.command_key)))
            if previous:
                if previous.command_hash != digest:
                    raise ObservationConflict("Ключ подготовки уже использован с другим содержимым")
                return await cls.item(session, previous, continuation, scope)
        if source.workflow_type != 'maintenance' or source.customer_id is None:
            raise ValueError("Подготовка акта требует исходное ТО с клиентом")
        observations = []
        for selected in payload.observations:
            observation = await Observations.get(session, selected.observation_id, scope, lock=True)
            if (observation.source_order_id, observation.customer_id, observation.customer_branch_id,
                observation.tenant_id, observation.storefront_id) != (source.id, source.customer_id, source.customer_branch_id, source.tenant_id, source.storefront_id):
                raise ValueError("Выберите замечания одного исходного ТО, клиента и объекта")
            if observation.version != selected.expected_version:
                raise ObservationConflict("Замечание уже изменено. Перечитайте актуальную версию.")
            observations.append(observation)
        # Freeze customer/object during snapshot collection; ordinary updates wait.
        customer = await session.scalar(select(Customer).where(Customer.id == source.customer_id,
            Customer.tenant_id == source.tenant_id).with_for_update().execution_options(populate_existing=True))
        if customer is None:
            raise ObservationNotFound("Клиент исходного ТО не найден")
        if source.customer_branch_id:
            branch = await session.scalar(select(CustomerBranch).where(CustomerBranch.id == source.customer_branch_id)
                .with_for_update().execution_options(populate_existing=True))
            if branch is None or branch.customer_id != source.customer_id:
                raise ObservationConflict("Принадлежность объекта изменилась. Перечитайте исходное ТО.")
        issuer = await session.scalar(select(DocumentLegalEntity).where(DocumentLegalEntity.id == payload.legal_entity_id,
            DocumentLegalEntity.tenant_id == scope.tenant_id, DocumentLegalEntity.status == 'active').with_for_update())
        if not issuer:
            raise ObservationNotFound("Выберите активное юридическое лицо исполнителя в настройках документов")
        if continuation is None:
            order = Order(tenant_id=source.tenant_id, storefront_id=source.storefront_id, customer_id=source.customer_id,
                          customer_branch_id=source.customer_branch_id, delivery_address=source.delivery_address,
                          status=OrderStatus.NEGOTIATION, workflow_type='repair', title=f"Замечания по ТО #{source.id}",
                          technical_meta={'maintenance_source_order_id': source.id})
            session.add(order); await session.flush()
            continuation = MaintenanceContinuation(source_order_id=source.id, order_id=order.id, tenant_id=source.tenant_id,
                storefront_id=source.storefront_id, customer_id=source.customer_id, customer_branch_id=source.customer_branch_id, created_by=actor)
            session.add(continuation); await session.flush()
        preparation = MaintenanceActPreparation(continuation_id=continuation.id, command_key=str(payload.command_key), command_hash=digest, created_by=actor)
        session.add(preparation); await session.flush()
        for observation in observations:
            revision = await session.scalar(select(MaintenanceObservationRevision).where(
                MaintenanceObservationRevision.observation_id == observation.id, MaintenanceObservationRevision.version == observation.version))
            if not revision:
                raise ObservationConflict("У замечания отсутствует сохранённая ревизия")
            session.add(MaintenanceActSource(preparation_id=preparation.id, revision_id=revision.id))
        await session.flush()
        template_id = await cls.template(session, issuer=issuer, scope=scope, storage=storage)
        draft = await ManagedDocumentService.create_draft(session, tenant_scope=scope,
            selection=DocumentContextSelection(order_id=continuation.order_id, document_type=TYPE, legal_entity_id=issuer.id,
                issue_date=payload.issue_date, maintenance_preparation_id=preparation.id), template_id=template_id,
            replaces_document_id=payload.replaces_document_id, commit=False)
        preparation.document_id = draft.id; session.add(preparation)
        await session.flush()
        return await cls.item(session, preparation, continuation, scope)
