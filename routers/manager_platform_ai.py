"""Platform credential settings, separated from ordinary GlobalConfig."""

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import AuthenticatedUser, require_system_owner_access
from routers.manager_permission_policy import ManagerPermissionRoute
from routers import manager_operation_ids as operation_ids
from services.platform_ai_connection_service import PlatformAIConnectionService
from services.zaprosu_provider_service import ZaprosuError
from services.deepseek_connection_service import DeepSeekConnectionService, DeepSeekCredentialError
from services.deepseek_provider_service import DefectActAIProviderError

logger = logging.getLogger(__name__)

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


class DeepseekConnectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str | None = Field(default=None, max_length=4096)
    enabled: bool | None = None


class DeepseekConnectionStatus(BaseModel):
    configured: bool
    enabled: bool
    source: Literal["settings", "environment", "none"]
    environment_key_available: bool


class DeepseekConnectionTest(BaseModel):
    ok: bool


def _raise_deepseek_safe(exc: DeepSeekCredentialError | DefectActAIProviderError) -> None:
    if exc.code in {"credential_store_unavailable", "credential_unreadable"}:
        status = 503
    elif exc.code == "already_configured":
        status = 409
    elif isinstance(exc, DefectActAIProviderError) or exc.code == "invalid_response":
        status = 502
    else:
        status = 422
    raise HTTPException(status_code=status, detail={"code": exc.code}) from None


@router.get("/deepseek", response_model=DeepseekConnectionStatus, operation_id=operation_ids.GET_DEEPSEEK_CONNECTION)
async def get_deepseek_connection(session: AsyncSession = Depends(get_session)):
    return DeepSeekConnectionService.public(await DeepSeekConnectionService.get(session))


@router.put("/deepseek", response_model=DeepseekConnectionStatus, operation_id=operation_ids.PUT_DEEPSEEK_CONNECTION)
async def put_deepseek_connection(payload: DeepseekConnectionUpdate, session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_system_owner_access)):
    try:
        result = await DeepSeekConnectionService.save(session, key=payload.key, enabled=payload.enabled)
    except DeepSeekCredentialError as exc:
        _raise_deepseek_safe(exc)
    logger.info("PLATFORM_AI_SETTINGS provider=deepseek actor=%s action=save key_replaced=%s enabled=%s", auth.username, bool((payload.key or "").strip()), result["enabled"])
    return result


@router.delete("/deepseek", response_model=DeepseekConnectionStatus, operation_id=operation_ids.DELETE_DEEPSEEK_CONNECTION)
async def delete_deepseek_connection(session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_system_owner_access)):
    result = await DeepSeekConnectionService.delete(session)
    logger.info("PLATFORM_AI_SETTINGS provider=deepseek actor=%s action=delete", auth.username)
    return result


@router.post("/deepseek/import-environment", response_model=DeepseekConnectionStatus, operation_id=operation_ids.IMPORT_DEEPSEEK_ENVIRONMENT_KEY)
async def import_deepseek_environment_key(session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_system_owner_access)):
    try:
        result = await DeepSeekConnectionService.import_environment(session)
    except DeepSeekCredentialError as exc:
        _raise_deepseek_safe(exc)
    logger.info("PLATFORM_AI_SETTINGS provider=deepseek actor=%s action=import_environment", auth.username)
    return result


@router.post("/deepseek/test", response_model=DeepseekConnectionTest, operation_id=operation_ids.TEST_DEEPSEEK_CONNECTION)
async def test_deepseek_connection(session: AsyncSession = Depends(get_session)):
    try:
        return await DeepSeekConnectionService.test(session)
    except (DeepSeekCredentialError, DefectActAIProviderError) as exc:
        _raise_deepseek_safe(exc)
