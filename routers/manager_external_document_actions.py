"""Project shared external evidence commands onto legacy-compatible Manager routes."""

from collections.abc import Awaitable, Callable, Sequence
from typing import Any
from urllib.parse import quote

from fastapi import Response, UploadFile
from pydantic import ValidationError

from core.command_actor import CommandActor
from core.manager_api_errors import manager_http_error
from core.manager_error_codes import BAD_REQUEST, DOCUMENT_NOT_FOUND
from models import OrderDocument, OrderDocumentExternalFile
from modules.documents.application.external_order_documents import (
    ExternalDocumentConflictError,
    ExternalDocumentFileSource,
    ExternalOrderDocumentPayload,
    ExternalOrderDocumentService,
)
from modules.documents.application.facsimile_context import FacsimilePdfError
from modules.documents.application.facsimile_preview import render_pdf_page_png
from schemas_manager_orders import ManagerOrderDocumentExternalFile, ManagerOrderDocumentItem
from services.document_service import DocumentService
from services.document_upload_validation import EXTERNAL_DOCUMENT_MAX_BYTES, ExternalDocumentValidationUnavailable
from services.public_write_idempotency_service import PublicWriteIdempotencyConflict, PublicWriteIdempotencyUnavailable


def document_item(
    document: OrderDocument,
    files: Sequence[OrderDocumentExternalFile] = (),
    basis: dict[str, Any] | None = None,
) -> ManagerOrderDocumentItem:
    origin = document.origin or (
        "native_generated" if DocumentService._is_native_managed_document(document) else "legacy"
    )
    basis_fields = {
        **(basis or {}),
        "base_document_id": document.base_document_id,
        "base_customer_contract_id": document.base_customer_contract_id,
    }
    return ManagerOrderDocumentItem(
        id=document.id, proposal_id=document.proposal_id, **basis_fields,
        scope_customer_branch_id=document.scope_customer_branch_id,
        scope_title=document.scope_title, scope_address=document.scope_address,
        scope_meta=document.scope_meta or {}, doc_type=document.doc_type,
        number=document.number, date=document.date, edit_url=document.google_edit_url,
        is_downloadable=bool(document.google_file_id or (files and origin == "external_upload")),
        origin=origin, external_status=document.external_status, status=document.status,
        file_version=files[0].version if files else 0,
        external_files=[ManagerOrderDocumentExternalFile.model_validate(file) for file in files],
    )


async def _source(file: UploadFile, endpoint: str) -> ExternalDocumentFileSource:
    content = await file.read(EXTERNAL_DOCUMENT_MAX_BYTES + 1)
    if len(content) > EXTERNAL_DOCUMENT_MAX_BYTES:
        raise manager_http_error(
            status_code=413, endpoint=endpoint, error_code="external_document_file_too_large",
            message="Размер файла превышает 10 МБ.",
        )
    return ExternalDocumentFileSource.from_bytes(content, file.filename or "", file.content_type or "")


def _error(endpoint: str, exc: Exception):
    if isinstance(exc, LookupError):
        return manager_http_error(status_code=404, endpoint=endpoint, error_code=DOCUMENT_NOT_FOUND, message=str(exc))
    if isinstance(exc, (ExternalDocumentConflictError, PublicWriteIdempotencyConflict)):
        return manager_http_error(status_code=409, endpoint=endpoint, error_code="external_document_conflict", message=str(exc))
    if isinstance(exc, (ExternalDocumentValidationUnavailable, PublicWriteIdempotencyUnavailable)):
        return manager_http_error(status_code=503, endpoint=endpoint, error_code="external_document_unavailable", message=str(exc))
    message = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
    return manager_http_error(status_code=400, endpoint=endpoint, error_code=BAD_REQUEST, message=message)


async def _result(session, auth, endpoint: str, operation: Callable[[], Awaitable]) -> ManagerOrderDocumentItem:
    try:
        outcome = await operation()
        service = ExternalOrderDocumentService
        scope = auth.tenant_scope()
        document = await service.get_document(session, scope, outcome.value.document_id)
        files = await service.files_by_document(session, scope, [document])
        basis_documents = [document]
        if document.base_document_id:
            try:
                base = await service.get_document(session, scope, document.base_document_id)
            except LookupError:
                pass
            else:
                if base.order_id == document.order_id:
                    basis_documents.append(base)
        basis = await DocumentService.build_document_basis_lookup(session, basis_documents)
        return document_item(document, files.get(document.id, []), basis.get(document.id))
    except (LookupError, ValueError, ExternalDocumentValidationUnavailable, PublicWriteIdempotencyUnavailable) as exc:
        raise _error(endpoint, exc) from exc


async def create_external_document(session, auth, endpoint, order_id, payload, file, idempotency_key):
    async def operation():
        return await ExternalOrderDocumentService.create(
            session, actor=CommandActor.from_auth(auth), order_id=order_id,
            payload=ExternalOrderDocumentPayload.model_validate(payload),
            idempotency_key=idempotency_key or "",
            source=await _source(file, endpoint) if file is not None else None,
        )

    return await _result(session, auth, endpoint, operation)


async def attach_external_document(session, auth, endpoint, doc_id, file, file_role, expected_version, idempotency_key):
    async def operation():
        if expected_version is None or file_role is None:
            raise ValueError("Укажите роль файла и ожидаемую версию документа.")
        return await ExternalOrderDocumentService.attach(
            session, actor=CommandActor.from_auth(auth), document_id=doc_id,
            file_role=file_role, expected_version=expected_version,
            idempotency_key=idempotency_key or "", source=await _source(file, endpoint),
        )

    return await _result(session, auth, endpoint, operation)


async def download_external_document(session, tenant_scope, endpoint, doc_id, file_version, preview, preview_page):
    try:
        result = await ExternalOrderDocumentService.read_file(
            session, tenant_scope=tenant_scope, document_id=doc_id, version=file_version,
        )
        if result is None:
            if preview:
                raise ValueError("Предпросмотр доступен для сохранённого внешнего PDF.")
            return None
        record, content = result
        headers = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
        if preview:
            if record.mime_type != "application/pdf":
                raise ValueError("Предпросмотр доступен только для PDF.")
            return Response(await render_pdf_page_png(content, preview_page), media_type="image/png", headers=headers)
        headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(record.filename)}"
        return Response(content, media_type=record.mime_type, headers=headers)
    except (LookupError, ValueError, FacsimilePdfError) as exc:
        raise _error(endpoint, exc) from exc
