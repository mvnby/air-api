from __future__ import annotations


from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.security import AuthenticatedUser, require_manager_access
from modules.documents.application.legal_entities import (
    DocumentLegalEntityConflictError,
    DocumentLegalEntityError,
    DocumentLegalEntityNotFoundError,
    DocumentLegalEntityService,
)
from modules.documents.application.number_policies import (
    DocumentNumberPolicyError,
    DocumentNumberPolicyNotFoundError,
    DocumentNumberPolicyService,
)
from routers.manager_operation_ids import (
    CREATE_MANAGER_DOCUMENT_LEGAL_ENTITY,
    LIST_MANAGER_DOCUMENT_LEGAL_ENTITIES,
    LIST_MANAGER_DOCUMENT_NUMBER_POLICIES,
    PATCH_MANAGER_DOCUMENT_LEGAL_ENTITY,
    UPSERT_MANAGER_DOCUMENT_NUMBER_POLICY,
)
from routers.manager_permission_policy import ManagerPermissionRoute

from .schemas import (
    DocumentLegalEntityCreatePayload,
    DocumentLegalEntityItem,
    DocumentLegalEntityListResponse,
    DocumentLegalEntityUpdatePayload,
    DocumentNumberPolicyItem,
    DocumentNumberPolicyListResponse,
    DocumentNumberPolicyPayload,
)


router = APIRouter(
    prefix="/api/manager/document-system",
    tags=["manager-document-system"],
    dependencies=[Depends(require_manager_access)],
    route_class=ManagerPermissionRoute,
)


@router.get(
    "/legal-entities",
    response_model=DocumentLegalEntityListResponse,
    operation_id=LIST_MANAGER_DOCUMENT_LEGAL_ENTITIES,
)
async def list_document_legal_entities(
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> DocumentLegalEntityListResponse:
    rows = await DocumentLegalEntityService.list(
        session,
        tenant_scope=auth.tenant_scope(),
    )
    return DocumentLegalEntityListResponse(
        items=[DocumentLegalEntityItem.model_validate(row) for row in rows]
    )


@router.post(
    "/legal-entities",
    response_model=DocumentLegalEntityItem,
    operation_id=CREATE_MANAGER_DOCUMENT_LEGAL_ENTITY,
)
async def create_document_legal_entity(
    payload: DocumentLegalEntityCreatePayload,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> DocumentLegalEntityItem:
    try:
        row = await DocumentLegalEntityService.create(
            session,
            tenant_scope=auth.tenant_scope(),
            display_name=payload.display_name,
            slug=payload.slug,
            legal_name=payload.legal_name,
            unp=payload.unp,
            entity_type=payload.entity_type,
            is_vat_payer=payload.is_vat_payer,
            is_default=payload.is_default,
            requisites=payload.requisites.model_dump(exclude_none=True),
        )
    except DocumentLegalEntityConflictError as exc:
        raise manager_http_error(
            status_code=409,
            endpoint=CREATE_MANAGER_DOCUMENT_LEGAL_ENTITY,
            error_code="document_legal_entity_conflict",
            message=str(exc),
        ) from exc
    except DocumentLegalEntityError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_MANAGER_DOCUMENT_LEGAL_ENTITY,
            error_code="document_legal_entity_invalid",
            message=str(exc),
        ) from exc
    return DocumentLegalEntityItem.model_validate(row)


@router.patch(
    "/legal-entities/{legal_entity_id}",
    response_model=DocumentLegalEntityItem,
    operation_id=PATCH_MANAGER_DOCUMENT_LEGAL_ENTITY,
)
async def patch_document_legal_entity(
    legal_entity_id: int,
    payload: DocumentLegalEntityUpdatePayload,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> DocumentLegalEntityItem:
    changes = payload.model_dump(exclude_unset=True)
    if payload.requisites is not None:
        changes["requisites"] = payload.requisites.model_dump(exclude_none=True)
    try:
        row = await DocumentLegalEntityService.update(
            session,
            tenant_scope=auth.tenant_scope(),
            legal_entity_id=legal_entity_id,
            changes=changes,
        )
    except DocumentLegalEntityNotFoundError as exc:
        raise manager_http_error(
            status_code=404,
            endpoint=PATCH_MANAGER_DOCUMENT_LEGAL_ENTITY,
            error_code="document_legal_entity_not_found",
            message=str(exc),
        ) from exc
    except DocumentLegalEntityConflictError as exc:
        raise manager_http_error(
            status_code=409,
            endpoint=PATCH_MANAGER_DOCUMENT_LEGAL_ENTITY,
            error_code="document_legal_entity_conflict",
            message=str(exc),
        ) from exc
    except DocumentLegalEntityError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=PATCH_MANAGER_DOCUMENT_LEGAL_ENTITY,
            error_code="document_legal_entity_invalid",
            message=str(exc),
        ) from exc
    return DocumentLegalEntityItem.model_validate(row)


@router.get(
    "/legal-entities/{legal_entity_id}/number-policies",
    response_model=DocumentNumberPolicyListResponse,
    operation_id=LIST_MANAGER_DOCUMENT_NUMBER_POLICIES,
)
async def list_document_number_policies(
    legal_entity_id: int,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> DocumentNumberPolicyListResponse:
    try:
        items = await DocumentNumberPolicyService.list_effective(
            session,
            tenant_scope=auth.tenant_scope(),
            legal_entity_id=legal_entity_id,
        )
    except DocumentNumberPolicyNotFoundError as exc:
        raise manager_http_error(
            status_code=404,
            endpoint=LIST_MANAGER_DOCUMENT_NUMBER_POLICIES,
            error_code="document_legal_entity_not_found",
            message=str(exc),
        ) from exc
    return DocumentNumberPolicyListResponse(
        items=[
            DocumentNumberPolicyItem(
                legal_entity_id=item.legal_entity_id,
                document_type=item.policy.document_type,
                series=item.policy.series,
                period_mode=item.policy.period_mode,
                minimum_width=item.policy.minimum_width,
                persisted=item.persisted,
            )
            for item in items
        ]
    )


@router.put(
    "/legal-entities/{legal_entity_id}/number-policies/{document_type}",
    response_model=DocumentNumberPolicyItem,
    operation_id=UPSERT_MANAGER_DOCUMENT_NUMBER_POLICY,
)
async def upsert_document_number_policy(
    legal_entity_id: int,
    document_type: str,
    payload: DocumentNumberPolicyPayload,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> DocumentNumberPolicyItem:
    try:
        row = await DocumentNumberPolicyService.upsert(
            session,
            tenant_scope=auth.tenant_scope(),
            legal_entity_id=legal_entity_id,
            document_type=document_type,
            series=payload.series,
            period_mode=payload.period_mode,
            minimum_width=payload.minimum_width,
        )
    except DocumentNumberPolicyNotFoundError as exc:
        raise manager_http_error(
            status_code=404,
            endpoint=UPSERT_MANAGER_DOCUMENT_NUMBER_POLICY,
            error_code="document_legal_entity_not_found",
            message=str(exc),
        ) from exc
    except (DocumentNumberPolicyError, ValueError) as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=UPSERT_MANAGER_DOCUMENT_NUMBER_POLICY,
            error_code="document_number_policy_invalid",
            message=str(exc),
        ) from exc
    return DocumentNumberPolicyItem(
        legal_entity_id=row.legal_entity_id,
        document_type=row.document_type,
        series=row.series,
        period_mode=row.period_mode,
        minimum_width=row.minimum_width,
        persisted=True,
    )
