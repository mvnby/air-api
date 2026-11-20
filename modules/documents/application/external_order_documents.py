"""Typed external order evidence without changing native document lifecycle."""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, StringConstraints, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.command_actor import CommandActor
from models import OrderDocument, OrderDocumentExternalFile, OrderProposal
from models.common import OrderStatus
from models.tenancy import TenantScope
from modules.documents.application.errors import ManagedDocumentConflictError
from services.authenticated_command_service import AuthenticatedCommandService
from services.document_upload_validation import (
    EXTERNAL_DOCUMENT_MAX_BYTES, validate_external_document, validate_external_document_size,
)
from services.private_attachment_storage_service import (
    PrivateAttachmentStorage,
    VariantScopedPrivateAttachmentStorage,
    get_private_attachment_storage,
)
from services.public_write_idempotency_service import PublicWriteCommandResponse
from services.tenant_entity_access_service import TenantEntityAccessService


EXTERNAL_DOCUMENT_ORIGIN = "external_upload"
EXTERNAL_FILE_VARIANT_SCOPE = "order-document-external"
EXTERNAL_FILE_MAX_VERSIONS = 100
ExternalDocumentType = Literal["contract", "technical_inspection_act", "defect_act", "act", "other"]
ExternalDocumentStatus = Literal["received", "signed"]
ExternalDocumentFileRole = Literal["original", "signed_copy"]


class ExternalDocumentConflictError(ValueError):
    """The document or its current evidence state blocks the write."""


class ExternalDocumentVersionConflictError(ExternalDocumentConflictError):
    """The file history changed since the caller read it."""


class ExternalOrderDocumentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: ExternalDocumentType
    number: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    document_date: date
    external_status: ExternalDocumentStatus = "received"
    site_id: PositiveInt | None = None
    equipment_ids: list[PositiveInt] = Field(default_factory=list, max_length=100)
    base_document_id: PositiveInt | None = None
    proposal_id: PositiveInt | None = None

    @model_validator(mode="after")
    def validate_scope(self):
        if self.site_id is None and (
            self.equipment_ids or self.document_type in {"technical_inspection_act", "defect_act"}
        ):
            raise ValueError("Укажите объект для технического документа или оборудования.")
        if len(set(self.equipment_ids)) != len(self.equipment_ids):
            raise ValueError("Оборудование указано повторно.")
        if self.document_type == "contract" and self.base_document_id:
            raise ValueError("Внешний договор нельзя привязать к договору-основанию.")
        return self


@dataclass(frozen=True, slots=True)
class ExternalDocumentFileSource:
    filename: str
    mime_type: str
    source_file_id: str
    loader: Callable[[], Awaitable[bytes]]

    @classmethod
    def from_bytes(cls, content: bytes, filename: str, mime_type: str):
        async def load() -> bytes:
            return content

        return cls(filename, mime_type, f"sha256:{sha256(content).hexdigest()}", load)

    def fingerprint(self) -> dict[str, str]:
        return {
            "file_id": self.source_file_id,
            "filename": self.filename,
            "mime_type": self.mime_type,
        }


class ExternalDocumentWriteResult(BaseModel):
    document_id: int
    file_version: int


async def _scope_snapshot(session, tenant_scope, order_id, payload):
    if payload.site_id is None:
        return None, None, None, None
    from services.order_site_service import OrderSiteService

    site, equipment = await OrderSiteService.resolve_scope(
        session, tenant_scope, order_id, payload.site_id, payload.equipment_ids, lock=True,
    )
    items = [{
        **item.equipment.model_dump(mode="json", include={
            "id", "equipment_type", "display_name", "brand", "model", "serial",
            "inventory_number", "location_hint", "refrigerant_type",
        }),
        "components": [component.model_dump(mode="json", include={
            "id", "component_type", "title", "brand", "model", "serial", "inventory_number",
        }) for component in item.equipment.components if not component.is_archived],
    } for item in equipment]
    return site.customer_branch_id, site.title, site.address, {
        "site_id": site.id,
        "equipment_ids": [item.equipment_id for item in equipment],
        "equipment": items,
    }


async def _check_references(session, order, payload, tenant_scope):
    if payload.proposal_id is not None:
        proposal = await session.scalar(select(OrderProposal.id).where(
            OrderProposal.id == payload.proposal_id,
            OrderProposal.order_id == order.id,
            OrderProposal.is_archived.is_(False),
        ))
        if proposal is None:
            raise LookupError("Предложение не найдено в заказе.")
    if payload.base_document_id is not None:
        basis = await TenantEntityAccessService.get_order_document(
            session, payload.base_document_id, tenant_scope=tenant_scope,
        )
        if basis is None or basis.order_id != order.id or basis.tenant_id not in {None, order.tenant_id}:
            raise LookupError("Договор-основание не найден в заказе.")
        if basis.doc_type != "contract" or basis.status not in {None, "issued", "sent", "signed"}:
            raise ExternalDocumentConflictError("Выберите действующий договор-основание.")


async def _store_file(session, *, actor, document, version, role, source, storage):
    from services.external_document_scan import scan_external_document

    content = await source.loader()
    validate_external_document_size(content)
    await scan_external_document(content)
    filename, mime_type, extension = await asyncio.to_thread(
        validate_external_document, content, source.filename, source.mime_type,
        signed_copy=role == "signed_copy",
    )
    digest = sha256(content).hexdigest()
    scoped_storage = VariantScopedPrivateAttachmentStorage(
        storage or get_private_attachment_storage(), variant_scope=EXTERNAL_FILE_VARIANT_SCOPE,
    )
    # A fresh key cannot overwrite an existing version even if a previous DB
    # acknowledgement was lost. The private orphan reconciler handles leftovers.
    variant = f"tenant-{actor.tenant_scope.tenant_id}-document-{document.id}-v{version}-{uuid4().hex}"
    stored = await scoped_storage.save(
        content=content, content_hash=digest, extension=extension, content_type=mime_type, variant=variant,
    )
    session.add(OrderDocumentExternalFile(
        document_id=document.id,
        version=version,
        tenant_id=actor.tenant_scope.tenant_id,
        role=role,
        filename=filename,
        mime_type=mime_type,
        size_bytes=len(content),
        checksum_sha256=digest,
        provider=stored.provider,
        storage_key=stored.storage_key,
        uploaded_by_staff_user_id=actor.staff_user_id,
        uploaded_by=actor.username,
    ))


class ExternalOrderDocumentService:
    @classmethod
    async def create(
        cls, session: AsyncSession, *, actor: CommandActor, order_id: int,
        payload: ExternalOrderDocumentPayload, idempotency_key: str,
        source: ExternalDocumentFileSource | None = None,
        storage: PrivateAttachmentStorage | None = None,
    ):
        scope = actor.tenant_scope
        if source is None and payload.external_status == "signed":
            raise ValueError("Для подписанного документа требуется исходный файл.")
        if source is None and payload.document_type != "contract":
            raise ValueError("Для этого документа требуется файл.")
        await cls.get_order(session, scope, order_id)

        async def operation():
            order = await cls.get_order(session, scope, order_id, lock=True)
            if order.status == OrderStatus.CLOSED:
                raise ExternalDocumentConflictError("К завершённому заказу можно приложить подписанный экземпляр существующего документа.")
            if payload.document_type == "act" and payload.external_status == "signed":
                from modules.documents.application.order_completion_coverage import ensure_legacy_act_write_allowed

                try:
                    await ensure_legacy_act_write_allowed(session, order_id)
                except ManagedDocumentConflictError as exc:
                    raise ExternalDocumentConflictError(str(exc)) from exc
            await _check_references(session, order, payload, scope)
            branch_id, title, address, metadata = await _scope_snapshot(session, scope, order_id, payload)
            document = OrderDocument(
                tenant_id=scope.tenant_id, order_id=order_id, doc_type=payload.document_type,
                origin=EXTERNAL_DOCUMENT_ORIGIN, external_status=payload.external_status,
                date=datetime.combine(payload.document_date, time.min), number=payload.number,
                base_document_id=payload.base_document_id, proposal_id=payload.proposal_id,
                scope_customer_branch_id=branch_id, scope_title=title, scope_address=address,
                scope_meta=metadata,
            )
            session.add(document)
            await session.flush()
            if source is not None:
                await _store_file(session, actor=actor, document=document, version=1,
                                  role="original", source=source, storage=storage)
            return PublicWriteCommandResponse(
                ExternalDocumentWriteResult(document_id=document.id, file_version=int(source is not None)),
                resource_type="order_document", resource_id=document.id,
            )

        return await AuthenticatedCommandService.execute(
            session, actor=actor, command_name="order_document.external_create",
            idempotency_key=idempotency_key, response_model=ExternalDocumentWriteResult,
            payload={"order_id": order_id, **payload.model_dump(mode="json"),
                     "file": source.fingerprint() if source is not None else None},
            operation=operation,
        )

    @classmethod
    async def attach(
        cls, session: AsyncSession, *, actor: CommandActor, document_id: int,
        file_role: ExternalDocumentFileRole, expected_version: int, idempotency_key: str,
        source: ExternalDocumentFileSource, storage: PrivateAttachmentStorage | None = None,
    ):
        scope = actor.tenant_scope
        if file_role not in {"original", "signed_copy"} or expected_version < 0:
            raise ValueError("Некорректная роль или ожидаемая версия файла.")
        initial = await cls.get_document(session, scope, document_id)
        order_id = initial.order_id

        async def operation():
            order = await cls.get_order(session, scope, order_id, lock=True)
            document = await cls.get_document(session, scope, document_id, lock=True)
            if document.tenant_id != scope.tenant_id:
                raise ExternalDocumentConflictError("Исторический документ нельзя менять.")
            if file_role == "original" and (
                order.status == OrderStatus.CLOSED or document.origin != EXTERNAL_DOCUMENT_ORIGIN
                or document.external_status == "signed"
            ):
                raise ExternalDocumentConflictError("Исходный документ нельзя заменить.")
            if file_role == "signed_copy" and (
                document.status not in {None, "issued", "sent", "signed"}
                or document.doc_type not in {"contract", "technical_inspection_act", "defect_act", "act"}
            ):
                raise ExternalDocumentConflictError("Выберите существующий выпущенный или внешний документ.")
            latest = await cls.latest_version(session, scope, document_id)
            if latest != expected_version:
                raise ExternalDocumentVersionConflictError("Версия файла изменилась. Обновите документ и повторите операцию.")
            if latest >= EXTERNAL_FILE_MAX_VERSIONS:
                raise ExternalDocumentConflictError("Достигнут предел версий файла документа.")
            version = latest + 1
            await _store_file(session, actor=actor, document=document, version=version,
                              role=file_role, source=source, storage=storage)
            return PublicWriteCommandResponse(
                ExternalDocumentWriteResult(document_id=document.id, file_version=version),
                resource_type="order_document", resource_id=document.id,
            )

        return await AuthenticatedCommandService.execute(
            session, actor=actor, command_name="order_document.external_attach",
            idempotency_key=idempotency_key, response_model=ExternalDocumentWriteResult,
            payload={"document_id": document_id, "role": file_role, "expected_version": expected_version,
                     "file": source.fingerprint()}, operation=operation,
        )

    @staticmethod
    async def get_order(session, tenant_scope, order_id, *, lock=False):
        order = await TenantEntityAccessService.get_order(
            session, order_id, tenant_scope=tenant_scope, for_update=lock, populate_existing=lock,
        )
        if order is None or order.tenant_id != tenant_scope.tenant_id:
            raise LookupError("Заказ не найден.")
        return order

    @staticmethod
    async def get_document(session, tenant_scope, document_id, *, lock=False):
        document = await TenantEntityAccessService.get_order_document(
            session, document_id, tenant_scope=tenant_scope, for_update=lock,
        )
        if document is None or document.tenant_id not in {None, tenant_scope.tenant_id}:
            raise LookupError("Документ не найден.")
        if lock:
            await session.refresh(document)
        return document

    @staticmethod
    async def latest_version(session, tenant_scope, document_id):
        table = OrderDocumentExternalFile
        return (await session.scalar(select(table.version).where(
            table.document_id == document_id, table.tenant_id == tenant_scope.tenant_id,
        ).order_by(table.version.desc()).limit(1))) or 0

    @staticmethod
    async def files_by_document(
        session: AsyncSession, tenant_scope: TenantScope, documents: Sequence[OrderDocument],
    ) -> dict[int, list[OrderDocumentExternalFile]]:
        document_ids = [item.id for item in documents if item.tenant_id == tenant_scope.tenant_id]
        if not document_ids:
            return {}
        table = OrderDocumentExternalFile
        rows = await session.scalars(select(table).where(
            table.tenant_id == tenant_scope.tenant_id, table.document_id.in_(document_ids),
        ).order_by(table.document_id, table.version.desc()))
        result: dict[int, list[OrderDocumentExternalFile]] = {}
        for row in rows:
            result.setdefault(row.document_id, []).append(row)
        return result

    @classmethod
    async def read_file(cls, session, *, tenant_scope, document_id, version=None, storage=None):
        document = await cls.get_document(session, tenant_scope, document_id)
        if version is None and document.origin != EXTERNAL_DOCUMENT_ORIGIN:
            return None
        table = OrderDocumentExternalFile
        statement = select(table).where(
            table.tenant_id == tenant_scope.tenant_id, table.document_id == document_id,
        )
        if version is not None:
            statement = statement.where(table.version == version)
        else:
            statement = statement.order_by((table.role == "original").desc(), table.version.desc())
        row = await session.scalar(statement.limit(1))
        if row is None:
            raise LookupError("Файл документа не найден.")
        variant = PurePosixPath(row.storage_key).stem
        expected = f"{EXTERNAL_FILE_VARIANT_SCOPE}-tenant-{row.tenant_id}-document-{row.document_id}-v{row.version}-"
        if not variant.startswith(expected):
            raise ValueError("Не удалось проверить сохранённый файл документа.")
        selected_storage = storage or get_private_attachment_storage(row.provider)
        try:
            data = await selected_storage.read_bounded(row.storage_key, EXTERNAL_DOCUMENT_MAX_BYTES)
        except FileNotFoundError as exc:
            raise LookupError("Файл документа недоступен.") from exc
        if row.size_bytes != len(data) or sha256(data).hexdigest() != row.checksum_sha256:
            raise ValueError("Не удалось проверить сохранённый файл документа.")
        return row, data
