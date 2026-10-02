"""
Leads Inbox router — Order-based triage queue.

GET /api/manager/leads/counter  → LeadsCounterResponse
GET /api/manager/leads/inbox    → LeadsInboxListResponse
"""
from typing import Literal

from routers.manager_operation_ids import (
    GET_MANAGER_INBOX_DETAIL,
    SET_MANAGER_INBOX_READ,
    ARCHIVE_MANAGER_INBOX_ITEM,
    RESTORE_MANAGER_INBOX_ITEM,
    RECORD_MANAGER_INBOX_NO_ANSWER,
    SET_MANAGER_INBOX_TENDER,
)
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_manager_tenant_scope, get_current_username
from models.tenancy import TenantScope
from routers.manager_operation_ids import GET_MANAGER_LEADS_COUNTER, GET_MANAGER_LEADS_INBOX
from schemas import LeadsCounterResponse, LeadsInboxListResponse
from models import LeadSource
from schemas_leads_inbox import InboxArchivePayload, InboxNoAnswerPayload, InboxReadPayload, InboxTenderPayload, LeadsInboxDetailResponse
from services.leads_inbox_command_service import LeadsInboxCommandService
from services.leads_inbox_service import InboxError, LeadsInboxService
from services.unified_inbox_service import UnifiedInboxService

router = APIRouter(prefix="/api/manager/leads", tags=["manager-leads-inbox"])


@router.get("/counter", response_model=LeadsCounterResponse, operation_id=GET_MANAGER_LEADS_COUNTER)
async def get_leads_counter(
    username: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
) -> LeadsCounterResponse:
    """Fast counter for the Dashboard / Sidebar badge.
    Counts only orders with status 'new_lead'.
    """
    return await UnifiedInboxService.counts(session, username=username, tenant_scope=tenant_scope)


@router.get("/inbox", response_model=LeadsInboxListResponse, operation_id=GET_MANAGER_LEADS_INBOX)
async def get_leads_inbox(
    scope: str = Query("active", pattern="^(active|archive)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    search: str | None = Query(None, max_length=200),
    source: LeadSource | None = Query(None),
    unread_only: bool = Query(False),
    sort: Literal["newest", "deadline"] = Query("newest"),
    username: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
) -> LeadsInboxListResponse:
    """Unified inbox feed.

    scope=active  → unlinked, unarchived new_lead incoming records.
    scope=archive → canceled or linked to an existing order.
    """
    return await UnifiedInboxService.get_leads_inbox(
        session,
        tenant_scope=tenant_scope,
        scope=scope,
        page=page,
        limit=limit,
        search=search,
        source=source,
        username=username,
        unread_only=unread_only,
        sort=sort,
    )


async def _command(session, callback, **kwargs):
    try:
        return await callback(session, **kwargs)
    except InboxError as exc:
        await session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/inbox/{order_id}", response_model=LeadsInboxDetailResponse, operation_id=GET_MANAGER_INBOX_DETAIL)
async def get_inbox_detail(order_id: int, username: str = Depends(get_current_username),
        session: AsyncSession = Depends(get_session), tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope)):
    return await _command(session, LeadsInboxService.detail, order_id=order_id, username=username, tenant_scope=tenant_scope)


@router.put("/inbox/{order_id}/read", response_model=LeadsInboxDetailResponse, operation_id=SET_MANAGER_INBOX_READ)
async def set_inbox_read(order_id: int, payload: InboxReadPayload, username: str = Depends(get_current_username),
        session: AsyncSession = Depends(get_session), tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope)):
    return await _command(session, LeadsInboxCommandService.read, order_id=order_id, username=username,
        tenant_scope=tenant_scope, is_read=payload.is_read)


@router.post("/inbox/{order_id}/archive", response_model=LeadsInboxDetailResponse, operation_id=ARCHIVE_MANAGER_INBOX_ITEM)
async def archive_inbox_item(order_id: int, payload: InboxArchivePayload, username: str = Depends(get_current_username),
        session: AsyncSession = Depends(get_session), tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope)):
    return await _command(session, LeadsInboxCommandService.archive, order_id=order_id, username=username,
        tenant_scope=tenant_scope, payload=payload)


@router.post("/inbox/{order_id}/restore", response_model=LeadsInboxDetailResponse, operation_id=RESTORE_MANAGER_INBOX_ITEM)
async def restore_inbox_item(order_id: int, username: str = Depends(get_current_username),
        session: AsyncSession = Depends(get_session), tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope)):
    return await _command(session, LeadsInboxCommandService.restore, order_id=order_id, username=username, tenant_scope=tenant_scope)


@router.post("/inbox/{order_id}/no-answer", response_model=LeadsInboxDetailResponse, operation_id=RECORD_MANAGER_INBOX_NO_ANSWER)
async def record_inbox_no_answer(order_id: int, payload: InboxNoAnswerPayload, username: str = Depends(get_current_username),
        session: AsyncSession = Depends(get_session), tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope)):
    return await _command(session, LeadsInboxCommandService.no_answer, order_id=order_id, username=username,
        tenant_scope=tenant_scope, payload=payload)


@router.patch("/inbox/{order_id}/tender", response_model=LeadsInboxDetailResponse, operation_id=SET_MANAGER_INBOX_TENDER)
async def set_inbox_tender(order_id: int, payload: InboxTenderPayload, username: str = Depends(get_current_username),
        session: AsyncSession = Depends(get_session), tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope)):
    return await _command(session, LeadsInboxCommandService.tender_context, order_id=order_id,
        username=username, tenant_scope=tenant_scope, payload=payload)
