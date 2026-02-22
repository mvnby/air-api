from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from routers.manager_operation_ids import LIST_MANAGER_SETTINGS, UPDATE_MANAGER_SETTING
from schemas import ManagerSettingListResponse, ManagerSettingResponse, ManagerSettingUpdatePayload
from services.settings_service import SettingsService

router = APIRouter(
    prefix="/api/manager/settings",
    tags=["manager/settings"],
    dependencies=[Depends(get_current_username)]
)

@router.get("", response_model=ManagerSettingListResponse, operation_id=LIST_MANAGER_SETTINGS)
async def list_manager_settings(session: AsyncSession = Depends(get_session)):
    items = await SettingsService.get_all_settings(session)
    return ManagerSettingListResponse(items=items)

@router.put("/{key}", response_model=ManagerSettingResponse, operation_id=UPDATE_MANAGER_SETTING)
async def update_manager_setting(
    key: str, 
    payload: ManagerSettingUpdatePayload, 
    session: AsyncSession = Depends(get_session)
):
    setting = await SettingsService.update_setting(session, key, payload)
    return setting
