"""
Leads Inbox router — Order-based triage queue.

GET /api/manager/leads/counter  → LeadsCounterResponse
GET /api/manager/leads/inbox    → LeadsInboxListResponse
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_manager_tenant_scope, get_current_username
from models.tenancy import TenantScope
from routers.manager_operation_ids import GET_MANAGER_LEADS_COUNTER, GET_MANAGER_LEADS_INBOX
from schemas import LeadsCounterResponse, LeadsInboxListResponse
from services.order_service import OrderService

router = APIRouter(prefix="/api/manager/leads", tags=["manager-leads-inbox"])


@router.get("/counter", response_model=LeadsCounterResponse, operation_id=GET_MANAGER_LEADS_COUNTER)
async def get_leads_counter(
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
) -> LeadsCounterResponse:
    """Fast counter for the Dashboard / Sidebar badge.
    Counts only orders with status 'new_lead'.
    """
    count, has_new = await OrderService.get_new_lead_counter(
        session,
        tenant_scope=tenant_scope,
    )
    return LeadsCounterResponse(count=count, has_new=has_new)


@router.get("/inbox", response_model=LeadsInboxListResponse, operation_id=GET_MANAGER_LEADS_INBOX)
async def get_leads_inbox(
    scope: str = Query("active", pattern="^(active|archive)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
) -> LeadsInboxListResponse:
    """Unified inbox feed.

    scope=active  → new_lead + assessment, sorted by is_new DESC then created_at DESC.
    scope=archive → canceled.
    """
    return await OrderService.get_leads_inbox(
        session,
        tenant_scope=tenant_scope,
        scope=scope,
        page=page,
        limit=limit,
    )
