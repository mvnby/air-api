from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, time

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import (
    DocumentArtifact,
    DocumentTemplate,
    DocumentTemplateVersion,
    Order,
    OrderDocument,
    OrderStatus,
)
from models.tenancy import TenantScope
from modules.documents.domain import (
    DocumentLifecycleError,
    DocumentLifecycleState,
    DocumentNumberScope,
    DocumentStatus,
    new_internal_reference,
    numbering_policy_key,
    transition_document,
)
from modules.documents.infrastructure.artifact_storage import (
    DocumentArtifactStorage,
    StoredDocumentArtifact,
)
from modules.documents.infrastructure.numbering_repository import (
    DocumentNumberingRepository,
)
from modules.documents.infrastructure.renderers import (
    NativeDocxRenderer,
    PdfConverter,
)
from modules.documents.infrastructure.template_source_storage import (
    TemplateSourceStorage,
)

from .artifact_helpers import (
    artifact_basename,
    artifact_row,
    build_render_inputs,
    list_artifacts,
    stored_artifact,
)
from .context_builder import DocumentContextBuilder, DocumentContextSelection
from .errors import (
    ManagedDocumentConflictError,
    ManagedDocumentGenerationError,
    ManagedDocumentNotFoundError,
)
from .number_policies import DocumentNumberPolicyService
from .replacement_guard import lock_replacement_target


DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
PDF_CONTENT_TYPE = "application/pdf"


@dataclass(frozen=True, slots=True)
class IssuedDocumentResult:
    document: OrderDocument
    artifacts: tuple[DocumentArtifact, ...]


class ManagedDocumentService:
    """Application lifecycle for native immutable CRM documents.

    File rendering is deliberately outside the number-reservation transaction.
    A failed render therefore retains its reserved number on the draft and can
    be retried idempotently without reusing or skipping another identity.
    """

    @classmethod
    async def list_for_order(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        order_id: int,
    ) -> list[OrderDocument]:
        if (
            await cls._get_mutable_scoped_order(
                session,
                tenant_scope=tenant_scope,
                order_id=order_id,
                require_mutable=False,
            )
            is None
        ):
            raise ManagedDocumentNotFoundError("Заказ не найден")
        rows = (
            (
                await session.execute(
                    select(OrderDocument)
                    .where(OrderDocument.order_id == order_id)
                    .order_by(OrderDocument.created_at.desc(), OrderDocument.id.desc())
                )
            )
            .scalars()
            .all()
        )
        # Legacy rows are visible only through the already-proven scoped order.
        return [row for row in rows if row.tenant_id in {None, tenant_scope.tenant_id}]

    @classmethod
    async def get_document(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        document_id: int,
    ) -> OrderDocument:
        document = await cls._get_scoped_document(
            session,
            tenant_scope=tenant_scope,
            document_id=document_id,
            for_update=False,
        )
        if document is None:
            raise ManagedDocumentNotFoundError("Документ не найден")
        return document

    @classmethod
    async def list_artifacts(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        document_id: int,
    ) -> list[DocumentArtifact]:
        await cls.get_document(
            session,
            tenant_scope=tenant_scope,
            document_id=document_id,
        )
        return await cls._artifacts(session, tenant_scope.tenant_id, document_id)

    @staticmethod
    async def get_artifact(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        artifact_id: str,
    ) -> DocumentArtifact:
        artifact = (
            await session.execute(
                select(DocumentArtifact)
                .join(
                    OrderDocument,
                    OrderDocument.id == DocumentArtifact.order_document_id,
                )
                .join(Order, Order.id == OrderDocument.order_id)
                .where(
                    DocumentArtifact.id == artifact_id,
                    DocumentArtifact.tenant_id == tenant_scope.tenant_id,
                    OrderDocument.tenant_id == tenant_scope.tenant_id,
                    Order.tenant_id == tenant_scope.tenant_id,
                    Order.storefront_id == tenant_scope.storefront_id,
                )
            )
        ).scalar_one_or_none()
        if artifact is None:
            raise ManagedDocumentNotFoundError("Файл документа не найден")
        return artifact

    @staticmethod
    def stored_artifact(artifact: DocumentArtifact) -> StoredDocumentArtifact:
        return stored_artifact(artifact)

    @classmethod
    async def create_draft(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        selection: DocumentContextSelection,
        template_id: int | None = None,
        replaces_document_id: int | None = None,
    ) -> OrderDocument:
        order = await cls._get_mutable_scoped_order(
            session,
            tenant_scope=tenant_scope,
            order_id=selection.order_id,
            require_mutable=True,
        )
        if order is None:
            raise ManagedDocumentNotFoundError("Заказ не найден")
        template, version = await cls._active_native_template(
            session,
            tenant_scope=tenant_scope,
            legal_entity_id=selection.legal_entity_id,
            document_type=selection.document_type,
            template_id=template_id,
        )
        if replaces_document_id is not None:
            await lock_replacement_target(
                session,
                tenant_scope=tenant_scope,
                order_id=selection.order_id,
                document_type=selection.document_type,
                target_document_id=replaces_document_id,
            )

        snapshot = await DocumentContextBuilder.build(
            session,
            tenant_scope=tenant_scope,
            selection=selection,
        )
        internal_reference = new_internal_reference()
        issue_datetime = datetime.combine(selection.issue_date, time.min)
        document = OrderDocument(
            tenant_id=tenant_scope.tenant_id,
            legal_entity_id=selection.legal_entity_id,
            order_id=selection.order_id,
            proposal_id=snapshot["meta"].get("proposal_id"),
            base_document_id=snapshot["meta"].get("base_document_id"),
            base_customer_contract_id=snapshot["meta"].get("base_customer_contract_id"),
            document_template_id=template.id,
            template_version_id=version.id,
            scope_customer_branch_id=selection.scope_customer_branch_id,
            scope_title=selection.scope_title,
            scope_address=selection.scope_address,
            scope_meta={
                "service_line_ids": list(selection.scope_service_line_ids),
                "service_line_quantities": dict(
                    selection.scope_service_line_quantities or {}
                ),
                "product_line_ids": list(selection.scope_product_line_ids),
            },
            doc_type=str(selection.document_type).strip().lower(),
            business_role=snapshot["meta"].get("business_role"),
            status=DocumentStatus.DRAFT.value,
            internal_reference=internal_reference,
            snapshot_version=int(snapshot["schema_version"]),
            render_snapshot=snapshot,
            replaces_document_id=replaces_document_id,
            number=internal_reference,
            date=issue_datetime,
            google_file_id=None,
            google_edit_url=None,
        )
        session.add(document)
        await cls._commit(session, "Не удалось создать черновик документа")
        await session.refresh(document)
        return document

    @classmethod
    async def issue(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        document_id: int,
        template_storage: TemplateSourceStorage,
        artifact_storage: DocumentArtifactStorage,
        pdf_converter: PdfConverter,
    ) -> IssuedDocumentResult:
        document = await cls._get_scoped_document(
            session,
            tenant_scope=tenant_scope,
            document_id=document_id,
            for_update=True,
        )
        if document is None:
            raise ManagedDocumentNotFoundError("Документ не найден")
        if document.status in {
            DocumentStatus.ISSUED.value,
            DocumentStatus.SENT.value,
            DocumentStatus.SIGNED.value,
        }:
            return IssuedDocumentResult(
                document=document,
                artifacts=tuple(
                    await cls._artifacts(session, tenant_scope.tenant_id, document_id)
                ),
            )
        if document.status != DocumentStatus.DRAFT.value:
            raise ManagedDocumentConflictError(
                "Документ нельзя выпустить в текущем статусе"
            )
        if not document.internal_reference or not document.legal_entity_id:
            raise ManagedDocumentConflictError(
                "Черновик не относится к управляемому документному контуру"
            )
        if not document.render_snapshot or not document.template_version_id:
            raise ManagedDocumentConflictError(
                "У черновика отсутствует снимок или версия шаблона"
            )
        if document.replaces_document_id:
            await lock_replacement_target(
                session,
                tenant_scope=tenant_scope,
                order_id=document.order_id,
                document_type=document.doc_type,
                target_document_id=document.replaces_document_id,
                replacement_document_id=document.id,
            )

        template, version = await cls._load_document_template_version(
            session,
            tenant_scope=tenant_scope,
            document=document,
        )
        policy_key = numbering_policy_key(document.doc_type, document.business_role)
        policy = await DocumentNumberPolicyService.get_effective(
            session,
            tenant_scope=tenant_scope,
            legal_entity_id=document.legal_entity_id,
            policy_key=policy_key,
        )
        issued_on = document.official_date or document.date.date()
        period_key = policy.period_key(
            issued_on,
            basis_key=cls._basis_numbering_key(document),
        )
        reservation = await DocumentNumberingRepository.reserve(
            session,
            scope=DocumentNumberScope(
                tenant_id=tenant_scope.tenant_id,
                legal_entity_id=document.legal_entity_id,
                document_type=policy.document_type,
                series=policy.series,
                period_key=period_key,
            ),
            idempotency_key=f"issue:{document.internal_reference}",
            minimum_width=policy.minimum_width,
        )
        await DocumentNumberingRepository.attach_to_document(
            session,
            tenant_id=tenant_scope.tenant_id,
            reservation_id=reservation.reservation_id,
            document_id=document_id,
        )
        official_number = f"{reservation.number_value:0{policy.minimum_width}d}"
        snapshot = deepcopy(document.render_snapshot)
        values = snapshot.setdefault("values", {})
        values.update(
            {
                "document.internal_reference": document.internal_reference,
                "document.official_series": policy.series,
                "document.official_number": official_number,
                "document.official_full_number": reservation.number_text,
                "document.issued_on": issued_on.strftime("%d.%m.%Y"),
                "document.act_sequence_number": str(reservation.number_value),
            }
        )
        document.official_series = policy.series
        document.official_period_key = period_key
        document.official_number = official_number
        document.official_date = issued_on
        document.render_snapshot = snapshot
        session.add(document)
        await cls._commit(session, "Не удалось зарезервировать номер документа")

        try:
            source = await template_storage.read_persisted(
                tenant_id=tenant_scope.tenant_id,
                template_id=int(template.id),
                version=version.version,
                storage_key=version.source_storage_key,
                filename=str(version.source_filename or "template.docx"),
                checksum_sha256=version.checksum_sha256,
            )
            render_template, render_context = build_render_inputs(
                template=template,
                version=version,
                source=source,
                snapshot=snapshot,
            )
            rendered = NativeDocxRenderer().render(render_template, render_context)
            basename = artifact_basename(document.doc_type, reservation.number_text)
            pdf_content = await asyncio.to_thread(
                pdf_converter.convert_docx,
                rendered.content,
                filename=f"{basename}.docx",
            )
            stored_docx = await artifact_storage.save(
                tenant_id=tenant_scope.tenant_id,
                document_id=document_id,
                kind="rendered_docx",
                filename=f"{basename}.docx",
                content_type=DOCX_CONTENT_TYPE,
                content=rendered.content,
            )
            stored_pdf = await artifact_storage.save(
                tenant_id=tenant_scope.tenant_id,
                document_id=document_id,
                kind="pdf",
                filename=f"{basename}.pdf",
                content_type=PDF_CONTENT_TYPE,
                content=pdf_content,
            )
        except Exception as exc:
            raise ManagedDocumentGenerationError(
                "Документ сохранил номер, но генерация DOCX/PDF не завершилась; повторите выпуск"
            ) from exc

        document = await cls._get_scoped_document(
            session,
            tenant_scope=tenant_scope,
            document_id=document_id,
            for_update=True,
        )
        if document is None:
            raise ManagedDocumentNotFoundError("Документ не найден")
        if document.status != DocumentStatus.DRAFT.value:
            if document.status in {
                DocumentStatus.ISSUED.value,
                DocumentStatus.SENT.value,
                DocumentStatus.SIGNED.value,
            }:
                return IssuedDocumentResult(
                    document=document,
                    artifacts=tuple(
                        await cls._artifacts(
                            session, tenant_scope.tenant_id, document_id
                        )
                    ),
                )
            raise ManagedDocumentConflictError(
                "Статус документа изменился во время генерации"
            )

        existing = await cls._artifacts(session, tenant_scope.tenant_id, document_id)
        existing_kinds = {item.kind for item in existing}
        if "rendered_docx" not in existing_kinds:
            session.add(artifact_row(stored_docx))
        if "pdf" not in existing_kinds:
            session.add(artifact_row(stored_pdf))
        state = transition_document(
            cls._lifecycle_state(document),
            DocumentStatus.ISSUED,
        )
        cls._apply_lifecycle(document, state)
        await DocumentNumberingRepository.mark_assigned(
            session,
            tenant_id=tenant_scope.tenant_id,
            document_id=document_id,
        )
        if document.replaces_document_id:
            original = await cls._get_scoped_document(
                session,
                tenant_scope=tenant_scope,
                document_id=document.replaces_document_id,
                for_update=True,
            )
            if original is None or original.order_id != document.order_id:
                raise ManagedDocumentConflictError(
                    "Заменяемый документ больше недоступен"
                )
            try:
                replacement_state = transition_document(
                    cls._lifecycle_state(original),
                    DocumentStatus.REPLACED,
                    replacement_document_id=document_id,
                )
            except DocumentLifecycleError as exc:
                raise ManagedDocumentConflictError(
                    "Заменяемый документ изменил статус во время выпуска"
                ) from exc
            cls._apply_lifecycle(original, replacement_state)
            session.add(original)
        session.add(document)
        await cls._commit(session, "Не удалось завершить выпуск документа")
        await session.refresh(document)
        return IssuedDocumentResult(
            document=document,
            artifacts=tuple(
                await cls._artifacts(session, tenant_scope.tenant_id, document_id)
            ),
        )

    @classmethod
    async def void(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        document_id: int,
        reason: str,
    ) -> OrderDocument:
        document = await cls._get_scoped_document(
            session,
            tenant_scope=tenant_scope,
            document_id=document_id,
            for_update=True,
        )
        if document is None:
            raise ManagedDocumentNotFoundError("Документ не найден")
        state = transition_document(
            cls._lifecycle_state(document),
            DocumentStatus.VOID,
            void_reason=reason,
        )
        cls._apply_lifecycle(document, state)
        await DocumentNumberingRepository.mark_void(
            session,
            tenant_id=tenant_scope.tenant_id,
            document_id=document_id,
        )
        session.add(document)
        await cls._commit(session, "Не удалось аннулировать документ")
        await session.refresh(document)
        return document

    @staticmethod
    async def _get_mutable_scoped_order(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        order_id: int,
        require_mutable: bool,
    ) -> Order | None:
        order = (
            await session.execute(
                select(Order).where(
                    Order.id == order_id,
                    Order.tenant_id == tenant_scope.tenant_id,
                    Order.storefront_id == tenant_scope.storefront_id,
                )
            )
        ).scalar_one_or_none()
        if order is not None and require_mutable and order.status == OrderStatus.CLOSED:
            raise ManagedDocumentConflictError(
                "Заказ завершён: документы доступны только для просмотра и повторной отправки"
            )
        return order

    @staticmethod
    async def _active_native_template(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        legal_entity_id: int,
        document_type: str,
        template_id: int | None,
    ) -> tuple[DocumentTemplate, DocumentTemplateVersion]:
        statement = (
            select(DocumentTemplate, DocumentTemplateVersion)
            .join(
                DocumentTemplateVersion,
                DocumentTemplateVersion.template_id == DocumentTemplate.id,
            )
            .where(
                DocumentTemplate.tenant_id == tenant_scope.tenant_id,
                DocumentTemplate.legal_entity_id == legal_entity_id,
                DocumentTemplate.doc_type == str(document_type).strip().lower(),
                DocumentTemplate.is_active.is_(True),
                DocumentTemplateVersion.renderer == "docx",
                DocumentTemplateVersion.status == "active",
            )
            .order_by(
                DocumentTemplate.is_default.desc(),
                DocumentTemplate.sort_order,
                DocumentTemplate.id,
            )
        )
        if template_id is not None:
            statement = statement.where(DocumentTemplate.id == template_id)
        row = (await session.execute(statement)).first()
        if row is None:
            raise ManagedDocumentNotFoundError(
                "Для документа нет активной DOCX-версии шаблона"
            )
        return row[0], row[1]

    @staticmethod
    async def _get_scoped_document(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        document_id: int,
        for_update: bool,
    ) -> OrderDocument | None:
        statement = (
            select(OrderDocument)
            .join(Order, Order.id == OrderDocument.order_id)
            .where(
                OrderDocument.id == document_id,
                OrderDocument.tenant_id == tenant_scope.tenant_id,
                Order.tenant_id == tenant_scope.tenant_id,
                Order.storefront_id == tenant_scope.storefront_id,
            )
            .options(selectinload(OrderDocument.document_template))
        )
        if for_update:
            statement = statement.with_for_update()
        return (await session.execute(statement)).scalar_one_or_none()

    @staticmethod
    async def _load_document_template_version(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        document: OrderDocument,
    ) -> tuple[DocumentTemplate, DocumentTemplateVersion]:
        row = (
            await session.execute(
                select(DocumentTemplate, DocumentTemplateVersion)
                .join(
                    DocumentTemplateVersion,
                    DocumentTemplateVersion.template_id == DocumentTemplate.id,
                )
                .where(
                    DocumentTemplate.id == document.document_template_id,
                    DocumentTemplate.tenant_id == tenant_scope.tenant_id,
                    DocumentTemplate.legal_entity_id == document.legal_entity_id,
                    DocumentTemplateVersion.id == document.template_version_id,
                    DocumentTemplateVersion.renderer == "docx",
                )
            )
        ).first()
        if row is None:
            raise ManagedDocumentNotFoundError(
                "Зафиксированная версия шаблона не найдена"
            )
        return row[0], row[1]

    @staticmethod
    def _basis_numbering_key(document: OrderDocument) -> str | None:
        if document.base_document_id:
            return f"document-{document.base_document_id}"
        if document.base_customer_contract_id:
            return f"contract-{document.base_customer_contract_id}"
        return None

    @staticmethod
    async def _artifacts(
        session: AsyncSession,
        tenant_id: int,
        document_id: int,
    ) -> list[DocumentArtifact]:
        return await list_artifacts(session, tenant_id, document_id)

    @staticmethod
    def _lifecycle_state(document: OrderDocument) -> DocumentLifecycleState:
        try:
            status = DocumentStatus(str(document.status))
        except ValueError as exc:
            raise ManagedDocumentConflictError(
                "Документ не относится к управляемому жизненному циклу"
            ) from exc
        return DocumentLifecycleState(
            status=status,
            issued_at=document.issued_at,
            sent_at=document.sent_at,
            signed_at=document.signed_at,
            voided_at=document.voided_at,
            void_reason=document.void_reason,
        )

    @staticmethod
    def _apply_lifecycle(
        document: OrderDocument, state: DocumentLifecycleState
    ) -> None:
        document.status = state.status.value
        document.issued_at = state.issued_at
        document.sent_at = state.sent_at
        document.signed_at = state.signed_at
        document.voided_at = state.voided_at
        document.void_reason = state.void_reason

    @staticmethod
    async def _commit(session: AsyncSession, message: str) -> None:
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise ManagedDocumentConflictError(message) from exc
