"""Authenticated Manager preview and confirmation of tender source evidence."""

from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_manager_tenant_scope, get_current_username, require_system_manager_tenant_scope
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
    """
    Read locally saved reviewed Belzakupki evidence and private original-attachment metadata
    for an accessible order in the current tenant/storefront. Does not fetch new source
    detail or invoke AI. Missing order returns 404; missing/invalid source identity returns
    400. See [source review and equipment
    rules](https://github.com/mvnby/air-api/blob/main/docs/belzakupki-intake.md#manager-review-and-source-documents).

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        return await BelzakupkiSourceEquipmentService.card(session, order_id=order_id, scope=tenant_scope)
    except (LookupError, ValueError) as exc:
        raise _error(exc) from exc


@router.get("/{order_id}/source-equipment", response_model=ManagerOrderSourceEquipmentPreview, operation_id=GET_MANAGER_ORDER_SOURCE_EQUIPMENT)
async def get_manager_order_source_equipment(
    order_id: int, proposal_id: int | None = None, _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session), tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Preview exact catalog matches from locally reviewed source objects for an accessible
    scoped order and selected proposal. Reports price/stock, existing lines and reasons
    items cannot be added or need explicit restoration; no lines are changed. Missing order
    returns 404 and invalid proposal/source context 400. Returned preview_fingerprint is
    required by the explicit add command. See [source review and equipment
    rules](https://github.com/mvnby/air-api/blob/main/docs/belzakupki-intake.md#manager-review-and-source-documents).

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        return await BelzakupkiSourceEquipmentService.preview(session, order_id=order_id, scope=tenant_scope, proposal_id=proposal_id)
    except (LookupError, ValueError) as exc:
        raise _error(exc) from exc


@router.post("/{order_id}/source-equipment", response_model=SourceEquipmentPrefillResult, operation_id=ADD_MANAGER_ORDER_SOURCE_EQUIPMENT)
async def add_manager_order_source_equipment(
    order_id: int, payload: ManagerOrderSourceEquipmentAdd, _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session), tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Append explicitly selected exact source-equipment matches to a writable draft proposal
    in the current tenant/storefront; existing lines/prices/quantities are preserved.
    Rechecks preview_fingerprint under the order lock: changed proposal/source/price/stock
    returns 409. Missing order returns 404; invalid selection or read-only context 400.
    Repeat the same command_id and selection to reuse its stored result; restoring
    previously removed items requires explicit restore IDs. See [source review and equipment
    rules](https://github.com/mvnby/air-api/blob/main/docs/belzakupki-intake.md#manager-review-and-source-documents).

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Fetch fresh Belzakupki source detail for the accessible current-tenant/storefront order
    and build a reviewable customer/site/equipment/submission/terms draft. Registry lookup
    can add warnings. Does not save customer/order changes or invoke document AI. Missing
    order/source returns 404, invalid source identity 400 and source/configuration failure
    502. See [source review and equipment
    rules](https://github.com/mvnby/air-api/blob/main/docs/belzakupki-intake.md#manager-review-and-source-documents).

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        return await BelzakupkiEnrichmentService.preview(session, order_id=order_id, scope=tenant_scope)
    except (LookupError, ValueError, RuntimeError, httpx.HTTPError) as exc:
        raise _error(exc) from exc


@router.post(
    "/{order_id}/source-analyze", response_model=ManagerOrderSourcePreview,
    operation_id=ANALYZE_MANAGER_ORDER_SOURCE,
    dependencies=[Depends(require_system_manager_tenant_scope)],
)
async def analyze_manager_order_source(
    order_id: int,
    payload: ManagerOrderSourceAnalyze,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Run explicit external AI analysis of selected original source documents for an
    accessible order and return an editable preview. Requires system-tenant Manager access.
    May fetch originals and extract missing text; does not apply the draft or overwrite
    order/document values. Missing source/order returns 404, unknown/truncated document
    input 400 and source/provider failure 502. Repeating starts another analysis rather than
    replaying a receipt. See [source review and equipment
    rules](https://github.com/mvnby/air-api/blob/main/docs/belzakupki-intake.md#manager-review-and-source-documents).

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Apply reviewed Belzakupki evidence to an accessible order in the current
    tenant/storefront. Can attach/create the reviewed customer and address branches, save
    source metadata/terms, select a scenario and move a new lead to negotiation, copy
    selected originals privately and prefill exact equipment for sales+installation.
    Archived incoming records, conflicting customer/scenario or invalid originals return
    400; missing source/order 404, source failure 502. Existing private originals/equipment
    provenance can be reused, but no generic command receipt or expected_version check is
    supplied. See [source review and equipment
    rules](https://github.com/mvnby/air-api/blob/main/docs/belzakupki-intake.md#manager-review-and-source-documents).

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Fetch an original document identified by the accessible order’s saved Belzakupki source
    in the current tenant/storefront. Returns a private/no-store binary attachment with
    detected file type. Missing source/order/document returns 404; invalid identity or
    document above configured attachment-size limit 400; upstream/configuration failure 502.
    Download does not copy it into the order’s private attachments.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
