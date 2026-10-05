"""System-only Jev settings and read-only shadow report."""
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from core.database import get_session
from core.security import AuthenticatedUser, require_system_owner_access
from routers import manager_operation_ids as ids
from routers.manager_permission_policy import ManagerPermissionRoute
from services.jev_connection_service import JevConnectionService, JevCredentialError
from services.jev_provider_service import JevProviderError
from services.jev_shadow_service import JevShadowService
from schemas_jev import JevShadowReport

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/manager/platform-ai/jev", tags=["manager/platform-ai"],
    dependencies=[Depends(require_system_owner_access)], route_class=ManagerPermissionRoute)


class JevUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str | None = Field(default=None, max_length=4096)
    enabled: bool | None = None
    daily_budget_usd: float | None = Field(default=None, gt=0, le=5, allow_inf_nan=False)


class JevStatus(BaseModel):
    configured: bool
    enabled: bool
    model: str
    daily_budget_usd: float
    max_daily_requests: int
    today_requests: int
    today_budget_used_usd: float


class JevTest(BaseModel):
    ok: bool
    model: str


def raise_safe(exc):
    code = exc.code
    status = 503 if code in {"credential_store_unavailable", "credential_unreadable"} else 502 if isinstance(exc, JevProviderError) else 422
    raise HTTPException(status_code=status, detail={"code": code}) from None


@router.get("", response_model=JevStatus, operation_id=ids.GET_JEV_CONNECTION)
async def get_jev_connection(session=Depends(get_session)):
    return JevConnectionService.public(await JevConnectionService.get(session))


@router.put("", response_model=JevStatus, operation_id=ids.PUT_JEV_CONNECTION)
async def put_jev_connection(payload: JevUpdate, session=Depends(get_session), auth: AuthenticatedUser=Depends(require_system_owner_access)):
    try:
        result = await JevConnectionService.save(session, **payload.model_dump())
    except JevCredentialError as exc:
        raise_safe(exc)
    logger.info("PLATFORM_AI_SETTINGS provider=jev actor=%s action=save enabled=%s", auth.username, result["enabled"])
    return result


@router.delete("", response_model=JevStatus, operation_id=ids.DELETE_JEV_CONNECTION)
async def delete_jev_connection(session=Depends(get_session), auth: AuthenticatedUser=Depends(require_system_owner_access)):
    result = await JevConnectionService.delete(session)
    logger.info("PLATFORM_AI_SETTINGS provider=jev actor=%s action=delete", auth.username)
    return result


@router.post("/test", response_model=JevTest, operation_id=ids.TEST_JEV_CONNECTION)
async def test_jev_connection(session=Depends(get_session)):
    try:
        return await JevConnectionService.test(session)
    except (JevCredentialError, JevProviderError) as exc:
        raise_safe(exc)


@router.get("/shadow", response_model=JevShadowReport, operation_id=ids.GET_JEV_SHADOW_REPORT)
async def get_jev_shadow_report(source: Literal["email", "belzakupki"] | None=None,
    disagreements_only: bool=False, limit: int=Query(default=20, ge=1, le=100),
    session=Depends(get_session), auth: AuthenticatedUser=Depends(require_system_owner_access)):
    return await JevShadowService.report(session, tenant_id=auth.tenant_id, source=source,
                                         disagreements_only=disagreements_only, limit=limit)
