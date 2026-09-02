from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import (
    DocumentArtifact,
    DocumentLegalEntity,
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
from modules.documents.infrastructure.renderers import PdfConverter
from modules.documents.infrastructure.template_source_storage import (
    TemplateSourceStorage,
)

from .artifact_helpers import artifact_row, list_artifacts, stored_artifact
from .editable_draft import EditableDraftError
from .editable_draft_issue import load_editable_draft_for_issue
from .context_builder import DocumentContextBuilder, DocumentContextSelection
from .errors import (
    ManagedDocumentConflictError,
    ManagedDocumentGenerationError,
    ManagedDocumentNotFoundError,
)
from .number_policies import DocumentNumberPolicyService
from .issuance_artifacts import (
    assign_official_identity,
    render_and_store_issued_artifacts,
)
from .replacement_guard import lock_replacement_target
from .template_selection import (
    load_document_template_version,
    resolve_template_use_case,
    select_active_native_template,
)


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
        contract_scenario, business_role = resolve_template_use_case(selection)
        template, version = await select_active_native_template(
            session,
            tenant_scope=tenant_scope,
            legal_entity_id=selection.legal_entity_id,
            document_type=selection.document_type,
            template_id=template_id,
            contract_scenario=contract_scenario,
            business_role=business_role,
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
    async def delete_draft(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        document_id: int,
    ) -> None:
        """Delete only an unissued native draft without an official artifact."""
        document = await cls._get_scoped_document(
            session,
            tenant_scope=tenant_scope,
            document_id=document_id,
            for_update=True,
        )
        if document is None:
            raise ManagedDocumentNotFoundError("Документ не найден")
        if (
            document.status != DocumentStatus.DRAFT.value
            or document.official_number
            or document.issued_at
        ):
            raise ManagedDocumentConflictError(
                "Удалить можно только черновик до присвоения официального номера"
            )
        if await cls._artifacts(session, tenant_scope.tenant_id, document_id):
            raise ManagedDocumentConflictError(
                "Черновик уже содержит сформированные файлы и должен остаться в истории"
            )
        await session.delete(document)
        await cls._commit(session, "Не удалось удалить черновик документа")

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
        verified_remote_revision: str | None = None,
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

        template, version = await load_document_template_version(
            session,
            tenant_scope=tenant_scope,
            document=document,
        )
        editable_source: bytes | None = None
        required_placeholder_counts: dict[str, int] | None = None
        source_artifact = next(
            (
                item
                for item in await cls._artifacts(
                    session, tenant_scope.tenant_id, document_id
                )
                if item.kind == "source_docx"
            ),
            None,
        )
        if source_artifact is not None:
            try:
                issue_source = await load_editable_draft_for_issue(
                    session,
                    tenant_id=tenant_scope.tenant_id,
                    document_id=document_id,
                    source_artifact=source_artifact,
                    placeholder_schema=version.placeholder_schema or {},
                    artifact_storage=artifact_storage,
                    verified_remote_revision=verified_remote_revision,
                )
                editable_source = issue_source.content
                required_placeholder_counts = (
                    issue_source.required_placeholder_counts
                )
            except (EditableDraftError, FileNotFoundError, TypeError, ValueError) as exc:
                raise ManagedDocumentConflictError(
                    "Отредактированный черновик повреждён или потерял служебные поля выпуска"
                ) from exc
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
            number_text_formatter=lambda value: policy.format_number_text(
                period_key, value
            ),
            legacy_document_type=(
                document.doc_type
                if policy.period_mode == "calendar_year"
                and await cls._is_default_issuer(
                    session,
                    tenant_id=tenant_scope.tenant_id,
                    legal_entity_id=document.legal_entity_id,
                )
                else None
            ),
        )
        await DocumentNumberingRepository.attach_to_document(
            session,
            tenant_id=tenant_scope.tenant_id,
            reservation_id=reservation.reservation_id,
            document_id=document_id,
        )
        snapshot, values = assign_official_identity(
            document=document,
            policy=policy,
            reservation=reservation,
            period_key=period_key,
            issued_on=issued_on,
        )
        session.add(document)
        await cls._commit(session, "Не удалось зарезервировать номер документа")

        try:
            stored_docx, stored_pdf = await render_and_store_issued_artifacts(
                tenant_id=tenant_scope.tenant_id,
                document_id=document_id,
                document_type=document.doc_type,
                official_full_number=reservation.number_text,
                template=template,
                version=version,
                snapshot=snapshot,
                official_values=values,
                editable_source=editable_source,
                required_placeholder_counts=required_placeholder_counts,
                template_storage=template_storage,
                artifact_storage=artifact_storage,
                pdf_converter=pdf_converter,
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
    def _basis_numbering_key(document: OrderDocument) -> str | None:
        if document.base_document_id:
            return f"document-{document.base_document_id}"
        if document.base_customer_contract_id:
            return f"contract-{document.base_customer_contract_id}"
        return None

    @staticmethod
    async def _is_default_issuer(
        session: AsyncSession,
        *,
        tenant_id: int,
        legal_entity_id: int,
    ) -> bool:
        return (
            (
                await session.execute(
                    select(DocumentLegalEntity.id).where(
                        DocumentLegalEntity.id == legal_entity_id,
                        DocumentLegalEntity.tenant_id == tenant_id,
                        DocumentLegalEntity.is_default.is_(True),
                    )
                )
            ).scalar_one_or_none()
            is not None
        )

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
