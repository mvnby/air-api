"""Platform credential settings, separated from ordinary GlobalConfig."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import require_system_owner_access
from routers.manager_permission_policy import ManagerPermissionRoute
from routers import manager_operation_ids as operation_ids
from services.platform_ai_connection_service import PlatformAIConnectionService
from services.zaprosu_provider_service import ZaprosuError

router = APIRouter(
    prefix="/api/manager/platform-ai", tags=["manager/platform-ai"],
    dependencies=[Depends(require_system_owner_access)],
    route_class=ManagerPermissionRoute,
)


class ConnectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str | None = Field(default=None, max_length=4096)
    enabled: bool | None = None
    selected_model: str | None = Field(default=None, max_length=160)


class ConnectionStatus(BaseModel):
    configured: bool
    enabled: bool
    selected_model: str | None


class ModelList(BaseModel):
    items: list[str]


class InferenceTest(BaseModel):
    ok: bool
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None


def _raise_safe(exc: ZaprosuError) -> None:
    code = exc.code
    status = 503 if code in {"credential_store_unavailable", "credential_unreadable"} else 502 if exc.status or exc.retryable else 422
    raise HTTPException(status_code=status, detail={"code": code}) from None


@router.get("", response_model=ConnectionStatus, operation_id=operation_ids.GET_PLATFORM_AI_CONNECTION)
async def get_platform_ai(session: AsyncSession = Depends(get_session)):
    return PlatformAIConnectionService.public(await PlatformAIConnectionService.get(session))


@router.put("", response_model=ConnectionStatus, operation_id=operation_ids.PUT_PLATFORM_AI_CONNECTION)
async def put_platform_ai(payload: ConnectionUpdate, session: AsyncSession = Depends(get_session)):
    try:
        return await PlatformAIConnectionService.save(
            session, key=payload.key, enabled=payload.enabled, model=payload.selected_model,
        )
    except ZaprosuError as exc:
        _raise_safe(exc)


@router.delete("", response_model=ConnectionStatus, operation_id=operation_ids.DELETE_PLATFORM_AI_CONNECTION)
async def delete_platform_ai(session: AsyncSession = Depends(get_session)):
    await PlatformAIConnectionService.delete(session)
    return {"configured": False, "enabled": False, "selected_model": None}


@router.get("/models", response_model=ModelList, operation_id=operation_ids.GET_PLATFORM_AI_MODELS)
async def get_platform_ai_models(session: AsyncSession = Depends(get_session)):
    try:
        return {"items": await PlatformAIConnectionService.models(session)}
    except ZaprosuError as exc:
        _raise_safe(exc)


@router.post("/test", response_model=InferenceTest, operation_id=operation_ids.TEST_PLATFORM_AI_INFERENCE)
async def test_platform_ai(session: AsyncSession = Depends(get_session)):
    try:
        result = await PlatformAIConnectionService.test(session)
        return {"ok": bool(result.text.strip()), "model": result.model,
                "prompt_tokens": result.prompt_tokens, "completion_tokens": result.completion_tokens}
    except ZaprosuError as exc:
        _raise_safe(exc)
