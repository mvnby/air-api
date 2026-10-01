"""Authenticated Manager preview and confirmation of tender source evidence."""

from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_manager_tenant_scope, get_current_username
from models.tenancy import TenantScope
from routers.manager_operation_ids import (
    ADD_MANAGER_ORDER_SOURCE_EQUIPMENT, GET_MANAGER_ORDER_SOURCE_CARD, GET_MANAGER_ORDER_SOURCE_EQUIPMENT,
    ANALYZE_MANAGER_ORDER_SOURCE,
    APPLY_MANAGER_ORDER_SOURCE,
    DOWNLOAD_MANAGER_ORDER_SOURCE_DOCUMENT,
    GET_MANAGER_ORDER_SOURCE_PREVIEW,
)
from schemas_belzakupki_enrichment import (
    ManagerOrderSourceCard, ManagerOrderSourceEquipmentAdd, ManagerOrderSourceEquipmentPreview, SourceEquipmentPrefillResult,
    ManagerOrderSourceApply,
    ManagerOrderSourceApplyResult,
    ManagerOrderSourceAnalyze,
    ManagerOrderSourcePreview,
)
from services.belzakupki_enrichment_service import BelzakupkiEnrichmentService
from services.belzakupki_source_equipment_service import BelzakupkiSourceEquipmentService, SourceEquipmentPreviewChangedError


router = APIRouter(prefix="/api/manager/orders", tags=["manager-orders"])


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, SourceEquipmentPreviewChangedError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
        return HTTPException(status_code=404, detail="Source tender or document not found")
    return HTTPException(status_code=502, detail="Belzakupki source is unavailable")


@router.get("/{order_id}/source-card", response_model=ManagerOrderSourceCard, operation_id=GET_MANAGER_ORDER_SOURCE_CARD)
async def get_manager_order_source_card(
    order_id: int, _: str = Depends(get_current_username), session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        return await BelzakupkiSourceEquipmentService.card(session, order_id=order_id, scope=tenant_scope)
    except (LookupError, ValueError) as exc:
        raise _error(exc) from exc


@router.get("/{order_id}/source-equipment", response_model=ManagerOrderSourceEquipmentPreview, operation_id=GET_MANAGER_ORDER_SOURCE_EQUIPMENT)
async def get_manager_order_source_equipment(
    order_id: int, proposal_id: int | None = None, _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session), tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        return await BelzakupkiSourceEquipmentService.preview(session, order_id=order_id, scope=tenant_scope, proposal_id=proposal_id)
    except (LookupError, ValueError) as exc:
        raise _error(exc) from exc


@router.post("/{order_id}/source-equipment", response_model=SourceEquipmentPrefillResult, operation_id=ADD_MANAGER_ORDER_SOURCE_EQUIPMENT)
async def add_manager_order_source_equipment(
    order_id: int, payload: ManagerOrderSourceEquipmentAdd, _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session), tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        return await BelzakupkiSourceEquipmentService.add(session, order_id=order_id, scope=tenant_scope, payload=payload)
    except (LookupError, ValueError) as exc:
        await session.rollback()
        raise _error(exc) from exc


@router.get(
    "/{order_id}/source-preview", response_model=ManagerOrderSourcePreview,
    operation_id=GET_MANAGER_ORDER_SOURCE_PREVIEW,
)
async def get_manager_order_source_preview(
    order_id: int,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        return await BelzakupkiEnrichmentService.preview(session, order_id=order_id, scope=tenant_scope)
    except (LookupError, ValueError, RuntimeError, httpx.HTTPError) as exc:
        raise _error(exc) from exc


@router.post(
    "/{order_id}/source-analyze", response_model=ManagerOrderSourcePreview,
    operation_id=ANALYZE_MANAGER_ORDER_SOURCE,
)
async def analyze_manager_order_source(
    order_id: int,
    payload: ManagerOrderSourceAnalyze,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        return await BelzakupkiEnrichmentService.analyze(
            session, order_id=order_id, scope=tenant_scope, payload=payload,
        )
    except (LookupError, ValueError, RuntimeError, httpx.HTTPError) as exc:
        raise _error(exc) from exc


@router.post(
    "/{order_id}/source-apply", response_model=ManagerOrderSourceApplyResult,
    operation_id=APPLY_MANAGER_ORDER_SOURCE,
)
async def apply_manager_order_source(
    order_id: int,
    payload: ManagerOrderSourceApply,
    username: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        return await BelzakupkiEnrichmentService.apply(
            session, order_id=order_id, scope=tenant_scope, payload=payload, username=username,
        )
    except (LookupError, ValueError, RuntimeError, httpx.HTTPError) as exc:
        await session.rollback()
        raise _error(exc) from exc


@router.get(
    "/{order_id}/source-documents/{document_id}",
    operation_id=DOWNLOAD_MANAGER_ORDER_SOURCE_DOCUMENT,
)
async def download_manager_order_source_document(
    order_id: int,
    document_id: str,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        content, filename, mime_type = await BelzakupkiEnrichmentService.document(
            session, order_id=order_id, document_id=document_id, scope=tenant_scope,
        )
    except (LookupError, ValueError, RuntimeError, httpx.HTTPError) as exc:
        raise _error(exc) from exc
    return Response(
        content=content, media_type=mime_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        },
    )
