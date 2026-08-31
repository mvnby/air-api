from __future__ import annotations

import asyncio
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.security import AuthenticatedUser, require_manager_access
from modules.documents.application.template_versions import (
    MAX_NATIVE_TEMPLATE_BYTES,
    NativeTemplatePlaceholderContract,
    NativeTemplateVersionService,
    TemplateVersionConflictError,
    TemplateVersionError,
    TemplateVersionNotFoundError,
    TemplateVersionValidationError,
    preflight_native_docx,
)
from modules.documents.infrastructure.renderers import (
    NativeDocxRenderer,
    TableBlockSpec,
)
from modules.documents.infrastructure.template_source_storage import (
    PrivateTemplateSourceStorage,
)
from modules.documents.domain import (
    CONDITIONAL_FLAGS,
    LINE_ROW_PLACEHOLDERS,
    PAYMENT_SCHEDULE_ROW_PLACEHOLDERS,
    SCALAR_PLACEHOLDERS,
    SUPPORTED_NATIVE_DOCUMENT_TYPES,
)
from routers.manager_operation_ids import (
    ACTIVATE_MANAGER_NATIVE_TEMPLATE_VERSION,
    CREATE_MANAGER_NATIVE_DOCUMENT_TEMPLATE,
    DOWNLOAD_MANAGER_NATIVE_TEMPLATE_VERSION_SOURCE,
    GET_MANAGER_DOCUMENT_PDF_RUNTIME,
    GET_MANAGER_NATIVE_PLACEHOLDER_CATALOG,
    LIST_MANAGER_NATIVE_DOCUMENT_TEMPLATES,
    LIST_MANAGER_NATIVE_TEMPLATE_VERSIONS,
    UPDATE_MANAGER_NATIVE_DOCUMENT_TEMPLATE,
    UPLOAD_MANAGER_NATIVE_TEMPLATE_VERSION,
)
from routers.manager_permission_policy import ManagerPermissionRoute

from .schemas import (
    DocumentPdfRuntimeStatus,
    NativeDocumentTemplateCreatePayload,
    NativeDocumentTemplateItem,
    NativeDocumentTemplateListResponse,
    NativeDocumentTemplateUpdatePayload,
    NativeTemplatePlaceholderSchemaPayload,
    NativePlaceholderCatalogResponse,
    NativePlaceholderConditionItem,
    NativePlaceholderDescriptorItem,
    NativePlaceholderTableItem,
    NativeTemplateVersionItem,
    NativeTemplateVersionListResponse,
)


router = APIRouter(
    prefix="/api/manager/document-system",
    tags=["manager-document-system"],
    dependencies=[Depends(require_manager_access)],
    route_class=ManagerPermissionRoute,
)

_NATIVE_DOCUMENT_TYPE_PATTERN = (
    "^(" + "|".join(sorted(SUPPORTED_NATIVE_DOCUMENT_TYPES)) + ")$"
)


@router.get(
    "/placeholder-catalog",
    response_model=NativePlaceholderCatalogResponse,
    operation_id=GET_MANAGER_NATIVE_PLACEHOLDER_CATALOG,
)
async def get_native_placeholder_catalog(
    doc_type: str = Query(..., pattern=_NATIVE_DOCUMENT_TYPE_PATTERN),
) -> NativePlaceholderCatalogResponse:
    return NativePlaceholderCatalogResponse(
        document_type=doc_type,
        fields=[
            NativePlaceholderDescriptorItem(
                name=item.name,
                label=item.label,
                group=item.group,
                syntax=f"{{{{ {item.name} }}}}",
            )
            for item in SCALAR_PLACEHOLDERS
        ],
        conditions=[
            NativePlaceholderConditionItem(
                name=item.name,
                label=item.label,
                group=item.group,
                start_syntax=f"{{{{#if {item.name}}}}}",
                end_syntax=f"{{{{/if {item.name}}}}}",
            )
            for item in CONDITIONAL_FLAGS
        ],
        tables=[
            NativePlaceholderTableItem(
                name="lines",
                anchor_syntax="{{ lines }}",
                row_fields=[
                    NativePlaceholderDescriptorItem(
                        name=item.name,
                        label=item.label,
                        group=item.group,
                        syntax=f"{{{{ {item.name} }}}}",
                    )
                    for item in LINE_ROW_PLACEHOLDERS
                ],
            ),
            NativePlaceholderTableItem(
                name="payment_schedule",
                anchor_syntax="{{ payment_schedule }}",
                row_fields=[
                    NativePlaceholderDescriptorItem(
                        name=item.name,
                        label=item.label,
                        group=item.group,
                        syntax=f"{{{{ {item.name} }}}}",
                    )
                    for item in PAYMENT_SCHEDULE_ROW_PLACEHOLDERS
                ],
            ),
        ],
    )


@router.get(
    "/templates",
    response_model=NativeDocumentTemplateListResponse,
    operation_id=LIST_MANAGER_NATIVE_DOCUMENT_TEMPLATES,
)
async def list_native_document_templates(
    legal_entity_id: int = Query(..., gt=0),
    doc_type: str | None = Query(default=None, pattern="^[a-z][a-z0-9_-]{0,63}$"),
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> NativeDocumentTemplateListResponse:
    try:
        rows = await NativeTemplateVersionService.list_templates(
            session,
            tenant_scope=auth.tenant_scope(),
            legal_entity_id=legal_entity_id,
            doc_type=doc_type,
        )
    except TemplateVersionNotFoundError as exc:
        raise _template_error(
            404,
            LIST_MANAGER_NATIVE_DOCUMENT_TEMPLATES,
            "native_template_scope_not_found",
            exc,
        )
    return NativeDocumentTemplateListResponse(
        items=[NativeDocumentTemplateItem.model_validate(row) for row in rows]
    )


@router.post(
    "/templates",
    response_model=NativeDocumentTemplateItem,
    operation_id=CREATE_MANAGER_NATIVE_DOCUMENT_TEMPLATE,
)
async def create_native_document_template(
    payload: NativeDocumentTemplateCreatePayload,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> NativeDocumentTemplateItem:
    try:
        row = await NativeTemplateVersionService.create_template(
            session,
            tenant_scope=auth.tenant_scope(),
            legal_entity_id=payload.legal_entity_id,
            name=payload.name,
            doc_type=payload.doc_type,
            description=payload.description,
            contract_scenario=payload.contract_scenario,
            business_role=payload.business_role,
        )
    except TemplateVersionNotFoundError as exc:
        raise _template_error(
            404,
            CREATE_MANAGER_NATIVE_DOCUMENT_TEMPLATE,
            "native_template_scope_not_found",
            exc,
        )
    except TemplateVersionConflictError as exc:
        raise _template_error(
            409,
            CREATE_MANAGER_NATIVE_DOCUMENT_TEMPLATE,
            "native_template_conflict",
            exc,
        )
    except TemplateVersionError as exc:
        raise _template_error(
            400, CREATE_MANAGER_NATIVE_DOCUMENT_TEMPLATE, "native_template_invalid", exc
        )
    return NativeDocumentTemplateItem.model_validate(row)


@router.patch(
    "/templates/{template_id}",
    response_model=NativeDocumentTemplateItem,
    operation_id=UPDATE_MANAGER_NATIVE_DOCUMENT_TEMPLATE,
)
async def update_native_document_template(
    template_id: int,
    payload: NativeDocumentTemplateUpdatePayload,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> NativeDocumentTemplateItem:
    try:
        row = await NativeTemplateVersionService.update_template_metadata(
            session,
            tenant_scope=auth.tenant_scope(),
            legal_entity_id=payload.legal_entity_id,
            template_id=template_id,
            name=payload.name,
            description=payload.description,
            contract_scenario=payload.contract_scenario,
            business_role=payload.business_role,
        )
    except TemplateVersionNotFoundError as exc:
        raise _template_error(
            404,
            UPDATE_MANAGER_NATIVE_DOCUMENT_TEMPLATE,
            "native_template_not_found",
            exc,
        )
    except TemplateVersionConflictError as exc:
        raise _template_error(
            409,
            UPDATE_MANAGER_NATIVE_DOCUMENT_TEMPLATE,
            "native_template_conflict",
            exc,
        )
    except TemplateVersionError as exc:
        raise _template_error(
            400,
            UPDATE_MANAGER_NATIVE_DOCUMENT_TEMPLATE,
            "native_template_invalid",
            exc,
        )
    return NativeDocumentTemplateItem.model_validate(row)


@router.get(
    "/templates/{template_id}/versions",
    response_model=NativeTemplateVersionListResponse,
    operation_id=LIST_MANAGER_NATIVE_TEMPLATE_VERSIONS,
)
async def list_native_template_versions(
    template_id: int,
    legal_entity_id: int = Query(..., gt=0),
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> NativeTemplateVersionListResponse:
    try:
        rows = await NativeTemplateVersionService.list_versions(
            session,
            tenant_scope=auth.tenant_scope(),
            legal_entity_id=legal_entity_id,
            template_id=template_id,
        )
    except TemplateVersionNotFoundError as exc:
        raise _template_error(
            404, LIST_MANAGER_NATIVE_TEMPLATE_VERSIONS, "native_template_not_found", exc
        )
    return NativeTemplateVersionListResponse(
        items=[NativeTemplateVersionItem.model_validate(row) for row in rows]
    )


@router.post(
    "/templates/{template_id}/versions",
    response_model=NativeTemplateVersionItem,
    operation_id=UPLOAD_MANAGER_NATIVE_TEMPLATE_VERSION,
)
async def upload_native_template_version(
    template_id: int,
    legal_entity_id: int = Form(..., gt=0),
    placeholder_schema: str | None = Form(default=None),
    change_note: str | None = Form(default=None, max_length=1000),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> NativeTemplateVersionItem:
    content = await _read_upload_limited(file, MAX_NATIVE_TEMPLATE_BYTES)
    try:
        preflight_native_docx(content)
    except TemplateVersionError as exc:
        raise _template_error(
            400,
            UPLOAD_MANAGER_NATIVE_TEMPLATE_VERSION,
            "native_template_invalid",
            exc,
        ) from exc
    if placeholder_schema:
        try:
            schema = NativeTemplatePlaceholderSchemaPayload.model_validate_json(
                placeholder_schema
            )
        except Exception as exc:
            raise _template_error(
                400,
                UPLOAD_MANAGER_NATIVE_TEMPLATE_VERSION,
                "native_template_schema_invalid",
                exc,
            )
    else:
        try:
            renderer = NativeDocxRenderer()
            discovered = renderer.discover_placeholders(content)
            discovered_conditions = renderer.discover_conditions(content)
        except ValueError as exc:
            raise _template_error(
                400,
                UPLOAD_MANAGER_NATIVE_TEMPLATE_VERSION,
                "native_template_invalid",
                exc,
            ) from exc
        table_placeholders = {
            "lines": LINE_ROW_PLACEHOLDERS,
            "payment_schedule": PAYMENT_SCHEDULE_ROW_PLACEHOLDERS,
        }
        schema = NativeTemplatePlaceholderSchemaPayload(
            fields=[
                item.name for item in SCALAR_PLACEHOLDERS if item.name in discovered
            ],
            conditions=[
                item.name
                for item in CONDITIONAL_FLAGS
                if item.name in discovered_conditions
            ],
            tables=[
                {
                    "name": table_name,
                    "row_fields": [item.name for item in row_placeholders],
                }
                for table_name, row_placeholders in table_placeholders.items()
                if table_name in discovered
                or any(item.name in discovered for item in row_placeholders)
            ],
        )
    allowed_fields = {item.name for item in SCALAR_PLACEHOLDERS}
    allowed_conditions = {item.name for item in CONDITIONAL_FLAGS}
    allowed_tables = {
        "lines": {item.name for item in LINE_ROW_PLACEHOLDERS},
        "payment_schedule": {
            item.name for item in PAYMENT_SCHEDULE_ROW_PLACEHOLDERS
        },
    }
    if (
        set(schema.fields) - allowed_fields
        or set(schema.conditions) - allowed_conditions
        or any(
            item.name not in allowed_tables
            or set(item.row_fields) - allowed_tables.get(item.name, set())
            for item in schema.tables
        )
    ):
        raise _template_error(
            400,
            UPLOAD_MANAGER_NATIVE_TEMPLATE_VERSION,
            "native_template_schema_invalid",
            ValueError("Схема содержит неизвестные плейсхолдеры"),
        )
    try:
        contract = NativeTemplatePlaceholderContract.create(
            field_catalog=schema.fields,
            condition_catalog=schema.conditions,
            table_blocks=(
                TableBlockSpec(name=item.name, row_fields=frozenset(item.row_fields))
                for item in schema.tables
            ),
        )
        row = await NativeTemplateVersionService.upload_native_docx_version(
            session,
            tenant_scope=auth.tenant_scope(),
            legal_entity_id=legal_entity_id,
            template_id=template_id,
            filename=str(file.filename or "template.docx"),
            content=content,
            placeholder_contract=contract,
            storage=PrivateTemplateSourceStorage(_legacy_private_storage()),
            change_note=change_note,
        )
    except TemplateVersionNotFoundError as exc:
        raise _template_error(
            404,
            UPLOAD_MANAGER_NATIVE_TEMPLATE_VERSION,
            "native_template_not_found",
            exc,
        )
    except TemplateVersionConflictError as exc:
        raise _template_error(
            409,
            UPLOAD_MANAGER_NATIVE_TEMPLATE_VERSION,
            "native_template_version_conflict",
            exc,
        )
    except TemplateVersionValidationError as exc:
        raise manager_http_error(
            status_code=422,
            endpoint=UPLOAD_MANAGER_NATIVE_TEMPLATE_VERSION,
            error_code="native_template_validation_failed",
            message=str(exc),
            field_errors={
                f"{issue.location}:{index}": issue.message
                for index, issue in enumerate(exc.result.issues)
            },
        ) from exc
    except (TemplateVersionError, ValueError) as exc:
        raise _template_error(
            400, UPLOAD_MANAGER_NATIVE_TEMPLATE_VERSION, "native_template_invalid", exc
        )
    return NativeTemplateVersionItem.model_validate(row)


@router.post(
    "/templates/{template_id}/versions/{version_id}/activate",
    response_model=NativeTemplateVersionItem,
    operation_id=ACTIVATE_MANAGER_NATIVE_TEMPLATE_VERSION,
)
async def activate_native_template_version(
    template_id: int,
    version_id: int,
    legal_entity_id: int = Query(..., gt=0),
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> NativeTemplateVersionItem:
    try:
        row = await NativeTemplateVersionService.activate_version(
            session,
            tenant_scope=auth.tenant_scope(),
            legal_entity_id=legal_entity_id,
            template_id=template_id,
            version_id=version_id,
        )
    except TemplateVersionNotFoundError as exc:
        raise _template_error(
            404,
            ACTIVATE_MANAGER_NATIVE_TEMPLATE_VERSION,
            "native_template_version_not_found",
            exc,
        )
    except TemplateVersionConflictError as exc:
        raise _template_error(
            409,
            ACTIVATE_MANAGER_NATIVE_TEMPLATE_VERSION,
            "native_template_version_conflict",
            exc,
        )
    return NativeTemplateVersionItem.model_validate(row)


@router.get(
    "/templates/{template_id}/versions/{version_id}/source",
    response_class=Response,
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {}
            },
            "description": "Immutable DOCX template source",
        }
    },
    operation_id=DOWNLOAD_MANAGER_NATIVE_TEMPLATE_VERSION_SOURCE,
)
async def download_native_template_version_source(
    template_id: int,
    version_id: int,
    legal_entity_id: int = Query(..., gt=0),
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> Response:
    try:
        version = await NativeTemplateVersionService.get_version(
            session,
            tenant_scope=auth.tenant_scope(),
            legal_entity_id=legal_entity_id,
            template_id=template_id,
            version_id=version_id,
        )
        source_content = await PrivateTemplateSourceStorage(
            _legacy_private_storage()
        ).read_persisted(
            tenant_id=auth.tenant_id,
            template_id=template_id,
            version=version.version,
            storage_key=version.source_storage_key,
            filename=str(version.source_filename or "template.docx"),
            checksum_sha256=version.checksum_sha256,
        )
    except TemplateVersionNotFoundError as exc:
        raise _template_error(
            404,
            DOWNLOAD_MANAGER_NATIVE_TEMPLATE_VERSION_SOURCE,
            "native_template_version_not_found",
            exc,
        )
    except (FileNotFoundError, TypeError, ValueError):
        raise manager_http_error(
            status_code=409,
            endpoint=DOWNLOAD_MANAGER_NATIVE_TEMPLATE_VERSION_SOURCE,
            error_code="native_template_source_integrity_failed",
            message="Исходный DOCX шаблона поврежден или недоступен",
        )
    return Response(
        content=source_content,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{quote(str(version.source_filename or 'template.docx'))}"
            ),
        },
    )


@router.get(
    "/runtime/pdf",
    response_model=DocumentPdfRuntimeStatus,
    operation_id=GET_MANAGER_DOCUMENT_PDF_RUNTIME,
)
async def get_document_pdf_runtime() -> DocumentPdfRuntimeStatus:
    converter = _legacy_pdf_converter()
    health = await asyncio.to_thread(converter.health)
    return DocumentPdfRuntimeStatus(
        available=health.available,
        provider=health.provider,
        detail=health.detail,
    )


def _legacy_private_storage():
    """Resolve through the compatibility module so legacy test patches work."""
    from .router import get_private_attachment_storage

    return get_private_attachment_storage()


def _legacy_pdf_converter():
    from .router import _pdf_converter

    return _pdf_converter()


async def _read_upload_limited(file: UploadFile, limit: int) -> bytes:
    content = bytearray()
    while True:
        chunk = await file.read(min(1024 * 1024, limit + 1))
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > limit:
            raise manager_http_error(
                status_code=413,
                endpoint=UPLOAD_MANAGER_NATIVE_TEMPLATE_VERSION,
                error_code="native_template_too_large",
                message="Размер DOCX шаблона не может превышать 5 МБ",
            )
    if not content:
        raise manager_http_error(
            status_code=400,
            endpoint=UPLOAD_MANAGER_NATIVE_TEMPLATE_VERSION,
            error_code="native_template_empty",
            message="Файл шаблона пуст",
        )
    return bytes(content)


def _template_error(status_code: int, endpoint: str, code: str, exc: Exception):
    return manager_http_error(
        status_code=status_code,
        endpoint=endpoint,
        error_code=code,
        message=str(exc),
    )
