from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from schemas import (
    LeadCreatePayload,
    LeadListResponse,
    LeadLossPayload,
    LeadQualifyPayload,
    LeadQualifyResponse,
    LeadResponse,
    LeadUpdatePayload,
)
from services.lead_service import LeadService


router = APIRouter(prefix="/api/manager/leads", tags=["manager-leads"])


@router.get("", response_model=LeadListResponse, operation_id="get_manager_leads")
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
):
    try:
        return await LeadService.list_leads(
            session=session,
            page=page,
            limit=limit,
            status=status,
            source=source,
            search=search,
            overdue_only=overdue_only,
            include_archived=include_archived,
            sort=sort,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("", response_model=LeadResponse, operation_id="create_manager_lead")
async def create_manager_lead(
    payload: LeadCreatePayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await LeadService.create_lead(session=session, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{lead_id}", response_model=LeadResponse, operation_id="patch_manager_lead")
async def patch_manager_lead(
    lead_id: int,
    payload: LeadUpdatePayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        lead = await LeadService.update_lead(session=session, lead_id=lead_id, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.post("/{lead_id}/qualify", response_model=LeadQualifyResponse, operation_id="qualify_manager_lead")
async def qualify_manager_lead(
    lead_id: int,
    payload: LeadQualifyPayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        result = await LeadService.qualify_lead(session=session, lead_id=lead_id, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail="Lead not found")
    return result


@router.post("/{lead_id}/mark-lost", response_model=LeadResponse, operation_id="mark_manager_lead_lost")
async def mark_manager_lead_lost(
    lead_id: int,
    payload: LeadLossPayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        result = await LeadService.mark_lead_lost(session=session, lead_id=lead_id, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail="Lead not found")
    return result
