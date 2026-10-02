"""Inbox actions for raw contact leads (not Order identifiers)."""
from routers.manager_operation_ids import (
    GET_MANAGER_RAW_INBOX_LEAD,
    SET_MANAGER_RAW_INBOX_LEAD_READ,
    ARCHIVE_MANAGER_RAW_INBOX_LEAD,
    RESTORE_MANAGER_RAW_INBOX_LEAD,
    RECORD_MANAGER_RAW_INBOX_LEAD_NO_ANSWER,
)
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_session
from core.security import get_current_manager_tenant_scope, get_current_username
from models.tenancy import TenantScope
from schemas_leads_inbox import InboxArchivePayload, InboxNoAnswerPayload, InboxReadPayload, LeadsInboxDetailResponse
from services.raw_lead_inbox_service import RawLeadInboxService

router = APIRouter(prefix='/api/manager/leads/inbox/raw', tags=['manager-leads-inbox'])


async def command(session, lead_id, username, scope, action, payload=None):
    try:
        return await RawLeadInboxService.mutate(session, lead_id, username=username, tenant_scope=scope, action=action, payload=payload)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get('/{lead_id}', response_model=LeadsInboxDetailResponse, operation_id=GET_MANAGER_RAW_INBOX_LEAD)
async def detail(lead_id: int, username: str = Depends(get_current_username), session: AsyncSession = Depends(get_session),
                 tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope)):
    try:
        return await RawLeadInboxService.detail(session, lead_id, username=username, tenant_scope=tenant_scope)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.put('/{lead_id}/read', response_model=LeadsInboxDetailResponse, operation_id=SET_MANAGER_RAW_INBOX_LEAD_READ)
async def mark_read(lead_id: int, payload: InboxReadPayload, username: str = Depends(get_current_username),
                    session: AsyncSession = Depends(get_session), tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope)):
    return await command(session, lead_id, username, tenant_scope, 'read', payload)


@router.post('/{lead_id}/archive', response_model=LeadsInboxDetailResponse, operation_id=ARCHIVE_MANAGER_RAW_INBOX_LEAD)
async def archive(lead_id: int, payload: InboxArchivePayload, username: str = Depends(get_current_username),
                  session: AsyncSession = Depends(get_session), tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope)):
    return await command(session, lead_id, username, tenant_scope, 'archive', payload)


@router.post('/{lead_id}/restore', response_model=LeadsInboxDetailResponse, operation_id=RESTORE_MANAGER_RAW_INBOX_LEAD)
async def restore(lead_id: int, username: str = Depends(get_current_username), session: AsyncSession = Depends(get_session),
                  tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope)):
    return await command(session, lead_id, username, tenant_scope, 'restore')


@router.post('/{lead_id}/no-answer', response_model=LeadsInboxDetailResponse, operation_id=RECORD_MANAGER_RAW_INBOX_LEAD_NO_ANSWER)
async def no_answer(lead_id: int, payload: InboxNoAnswerPayload, username: str = Depends(get_current_username),
                    session: AsyncSession = Depends(get_session), tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope)):
    return await command(session, lead_id, username, tenant_scope, 'no-answer', payload)
