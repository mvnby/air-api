from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_owner_username
from routers.manager_operation_ids import CREATE_MANAGER_STAFF, LIST_MANAGER_STAFF, PATCH_MANAGER_STAFF
from schemas import ManagerStaffCreatePayload, ManagerStaffListResponse, ManagerStaffResponse, ManagerStaffUpdatePayload
from services.staff_user_service import StaffUserService


router = APIRouter(prefix="/api/manager/staff", tags=["manager-staff"])


@router.get("", response_model=ManagerStaffListResponse, operation_id=LIST_MANAGER_STAFF)
async def list_staff(
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=100),
    search: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_owner_username),
):
    return await StaffUserService.list_staff(session=session, page=page, limit=limit, search=search)


@router.post("", response_model=ManagerStaffResponse, operation_id=CREATE_MANAGER_STAFF)
async def create_staff(
    payload: ManagerStaffCreatePayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_owner_username),
):
    try:
        return await StaffUserService.create_staff(session=session, payload=payload)
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail="Логин или Telegram ID уже используется") from exc
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{staff_user_id}", response_model=ManagerStaffResponse, operation_id=PATCH_MANAGER_STAFF)
async def patch_staff(
    staff_user_id: int,
    payload: ManagerStaffUpdatePayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_owner_username),
):
    try:
        staff_user = await StaffUserService.update_staff(session=session, staff_user_id=staff_user_id, payload=payload)
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail="Логин или Telegram ID уже используется") from exc
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if staff_user is None:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    return staff_user
