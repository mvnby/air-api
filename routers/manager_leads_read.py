from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_manager_tenant_scope, get_current_username
from models.tenancy import TenantScope
from routers.manager_operation_ids import GET_MANAGER_LEADS
from schemas import LeadListResponse
from services.lead_service import LeadService


router = APIRouter(prefix="/api/manager/leads", tags=["manager-leads"])


@router.get("", response_model=LeadListResponse, operation_id=GET_MANAGER_LEADS)
async def get_manager_leads(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    overdue_only: bool = Query(False),
    include_archived: bool = Query(False),
    sort: str = Query("created_at_desc"),
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Page raw Lead records in the current tenant/storefront using
    status/source/search/overdue/sort filters; limit is at most 100. Without explicit
    status, the list selects new/contacted leads even when include_archived=true; archived
    rows are hidden unless requested. Invalid status/source returns 400; unknown sort falls
    back to newest first. This is the Lead list, not the unified Order+Lead incoming feed;
    reading does not mark personal read state.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        return await LeadService.list_leads(
            session=session,
            page=page,
            limit=limit,
            tenant_scope=tenant_scope,
            status=status,
            source=source,
            search=search,
            overdue_only=overdue_only,
            include_archived=include_archived,
            sort=sort,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
