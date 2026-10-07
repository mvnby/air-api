import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_owner_username, get_current_username
from routers.manager_operation_ids import (
    CREATE_MANAGER_SETTING,
    GET_FX_RATE,
    LIST_MANAGER_SETTINGS,
    SUGGEST_ADDRESS,
    UPDATE_MANAGER_SETTING,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas import (
    AddressSuggestResponse,
    FxRateResponse,
    ManagerSettingCreatePayload,
    ManagerSettingListResponse,
    ManagerSettingResponse,
    ManagerSettingUpdatePayload,
)
from services.address_suggest_service import AddressSuggestService
from services.settings_service import SettingsService
from services.fx_rate_service import FxRateService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/manager/settings",
    tags=["manager/settings"],
    dependencies=[Depends(get_current_username)],
    route_class=ManagerPermissionRoute,
)


@router.get("", response_model=ManagerSettingListResponse, operation_id=LIST_MANAGER_SETTINGS)
async def list_manager_settings(
    session: AsyncSession = Depends(get_session),
    _owner_username: str = Depends(get_current_owner_username),
):
    """
    Read global platform configuration keys, stored values and descriptions, ordered by key.
    Requires an owner/admin in the system tenant. These are platform-wide GlobalConfig values,
    not current-storefront settings, and the response is not a generic secret-masking interface.
    For storefront configuration use /api/manager/storefront-settings.
    """
    items = await SettingsService.get_all_settings(session)
    return ManagerSettingListResponse(items=items)


@router.get("/fx-rate", response_model=FxRateResponse, operation_id=GET_FX_RATE)
async def get_fx_rate(session: AsyncSession = Depends(get_session)):
    """
    Read effective platform USD/BYN and EUR/BYN rates for an authenticated Manager. In manual
    mode only USD has a manual value; EUR is null. In automatic mode rates come from the NBRB
    provider cache/request, with manual USD fallback if unavailable. The source field records
    the configured mode, not proof that a particular returned rate came from that provider.
    Unavailable rates are null; this route does not save a rate.
    """
    usd_rate = await FxRateService.get_effective_usd_byn_rate(session)
    eur_rate = await FxRateService.get_effective_eur_byn_rate(session)
    source = await FxRateService._get_rate_source(session)
    return FxRateResponse(
        usd_byn=float(usd_rate) if usd_rate else None,
        eur_byn=float(eur_rate) if eur_rate else None,
        source=source,
    )


@router.get("/address-suggest", response_model=AddressSuggestResponse, operation_id=SUGGEST_ADDRESS)
async def suggest_address(
    q: str = Query(..., min_length=2),
    lat: float | None = Query(default=None, ge=-90, le=90),
    lon: float | None = Query(default=None, ge=-180, le=180),
):
    """
    Query the external address-suggestion provider for an authenticated Manager without saving
    an address. q requires at least two characters; geographic bias is sent only when both lat
    and lon are present. Invalid parameters return 422, a service configuration/runtime error
    returns 500, and upstream HTTP failure returns 502. Suggestions are provider results, not a
    verified customer address.
    """
    try:
        ull = f"{lon},{lat}" if lat is not None and lon is not None else None
        return AddressSuggestResponse(
            items=await AddressSuggestService.suggest(q, ull=ull)
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        logger.error(
            "Yandex address suggest failed error_type=%s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail="Address suggestion service temporarily unavailable",
        )


@router.put("/{key}", response_model=ManagerSettingResponse, operation_id=UPDATE_MANAGER_SETTING)
async def update_manager_setting(
    key: str,
    payload: ManagerSettingUpdatePayload,
    session: AsyncSession = Depends(get_session),
    _owner_username: str = Depends(get_current_owner_username),
):
    """
    Replace the value of an existing global platform configuration key; update its description
    only when provided. Requires a system-tenant owner/admin. Missing keys return 404; use POST
    to create them. Commits immediately and updates the timestamp, without optimistic version
    checks or an Idempotency-Key receipt. This does not update tenant storefront settings.
    """
    setting = await SettingsService.update_setting(session, key, payload)
    return setting


@router.post("", response_model=ManagerSettingResponse, operation_id=CREATE_MANAGER_SETTING)
async def create_manager_setting(
    payload: ManagerSettingCreatePayload,
    session: AsyncSession = Depends(get_session),
    _owner_username: str = Depends(get_current_owner_username),
):
    """
    Create a global platform configuration key/value and optional description. Requires a
    system-tenant owner/admin. Existing keys return 400 rather than being overwritten, including
    a repeated successful request. Commits immediately; this is not tenant/storefront
    configuration and has no command replay receipt.
    """
    setting = await SettingsService.create_setting(
        session,
        payload.key,
        payload.value,
        payload.description,
    )
    return setting
