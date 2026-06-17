import logging
import httpx
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from routers.manager_operation_ids import CREATE_MANAGER_SETTING, GET_FX_RATE, LIST_MANAGER_SETTINGS, SUGGEST_ADDRESS, UPDATE_MANAGER_SETTING
from schemas import AddressSuggestResponse, ManagerSettingCreatePayload, ManagerSettingListResponse, ManagerSettingResponse, ManagerSettingUpdatePayload, FxRateResponse
from services.address_suggest_service import AddressSuggestService
from services.settings_service import SettingsService
from services.fx_rate_service import FxRateService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/manager/settings",
    tags=["manager/settings"],
    dependencies=[Depends(get_current_username)]
)

@router.get("", response_model=ManagerSettingListResponse, operation_id=LIST_MANAGER_SETTINGS)
async def list_manager_settings(session: AsyncSession = Depends(get_session)):
    items = await SettingsService.get_all_settings(session)
    return ManagerSettingListResponse(items=items)

@router.get("/fx-rate", response_model=FxRateResponse, operation_id=GET_FX_RATE)
async def get_fx_rate(session: AsyncSession = Depends(get_session)):
    usd_rate = await FxRateService.get_effective_usd_byn_rate(session)
    eur_rate = await FxRateService.get_effective_eur_byn_rate(session)
    source = await FxRateService._get_rate_source(session)
    return FxRateResponse(
        usd_byn=float(usd_rate) if usd_rate else None,
        eur_byn=float(eur_rate) if eur_rate else None,
        source=source
    )

@router.get("/address-suggest", response_model=AddressSuggestResponse, operation_id=SUGGEST_ADDRESS)
async def suggest_address(q: str = Query(..., min_length=2)):
    try:
        return AddressSuggestResponse(items=await AddressSuggestService.suggest(q))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except httpx.HTTPError:
        logger.exception("Yandex address suggest failed")
        raise HTTPException(status_code=502, detail="Address suggestion service temporarily unavailable")

@router.put("/{key}", response_model=ManagerSettingResponse, operation_id=UPDATE_MANAGER_SETTING)
async def update_manager_setting(
    key: str,
    payload: ManagerSettingUpdatePayload,
    session: AsyncSession = Depends(get_session)
):
    setting = await SettingsService.update_setting(session, key, payload)
    return setting


@router.post("", response_model=ManagerSettingResponse, operation_id=CREATE_MANAGER_SETTING)
async def create_manager_setting(
    payload: ManagerSettingCreatePayload,
    session: AsyncSession = Depends(get_session)
):
    setting = await SettingsService.create_setting(session, payload.key, payload.value, payload.description)
    return setting
