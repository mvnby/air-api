from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from routers.manager_operation_ids import (
    CREATE_MANAGER_LEAD,
    MARK_MANAGER_LEAD_LOST,
    PATCH_MANAGER_LEAD,
    QUALIFY_MANAGER_LEAD,
)
from schemas import (
    LeadCreatePayload,
    LeadLossPayload,
    LeadQualifyPayload,
    LeadQualifyResponse,
    LeadResponse,
    LeadUpdatePayload,
)
from services.lead_service import LeadService


router = APIRouter(prefix="/api/manager/leads", tags=["manager-leads"])


@router.post("", response_model=LeadResponse, operation_id=CREATE_MANAGER_LEAD)
async def create_manager_lead(
    payload: LeadCreatePayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await LeadService.create_lead(session=session, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{lead_id}", response_model=LeadResponse, operation_id=PATCH_MANAGER_LEAD)
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


@router.post("/{lead_id}/qualify", response_model=LeadQualifyResponse, operation_id=QUALIFY_MANAGER_LEAD)
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


@router.post("/{lead_id}/mark-lost", response_model=LeadResponse, operation_id=MARK_MANAGER_LEAD_LOST)
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
