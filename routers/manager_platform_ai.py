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
    """
    Read configured/enabled/selected_model state of the shared ZAPRO.SU platform connection.
    Requires a system-tenant owner/admin. Never returns the stored key and does not contact the
    provider; configured means a database connection record exists, not that live inference has
    succeeded.
    """
    return PlatformAIConnectionService.public(await PlatformAIConnectionService.get(session))


@router.put("", response_model=ConnectionStatus, operation_id=operation_ids.PUT_PLATFORM_AI_CONNECTION)
async def put_platform_ai(payload: ConnectionUpdate, session: AsyncSession = Depends(get_session)):
    """
    Save the shared ZAPRO.SU key, enabled flag and selected model; requires a system-tenant
    owner/admin. A nonblank key replaces encrypted credentials; blank/omitted key preserves
    them, so a first save needs a key. Omitted enabled/model preserve existing values; an empty
    model clears it. Enabling requires a model. Returns public state without secrets;
    invalid/not-configured values return 422 and credential-store errors 503 with detail.code.
    Saving does not test provider access and has no replay receipt.
    """
    try:
        return await PlatformAIConnectionService.save(
            session, key=payload.key, enabled=payload.enabled, model=payload.selected_model,
        )
    except ZaprosuError as exc:
        _raise_safe(exc)


@router.delete("", response_model=ConnectionStatus, operation_id=operation_ids.DELETE_PLATFORM_AI_CONNECTION)
async def delete_platform_ai(session: AsyncSession = Depends(get_session)):
    """
    Delete the shared ZAPRO.SU credential record and return configured=false, enabled=false,
    selected_model=null. Requires a system-tenant owner/admin. Repeating after deletion returns
    the same public state. This removes local credentials; it does not revoke the provider-side
    key or issue a provider call.
    """
    await PlatformAIConnectionService.delete(session)
    return {"configured": False, "enabled": False, "selected_model": None}


@router.get("/models", response_model=ModelList, operation_id=operation_ids.GET_PLATFORM_AI_MODELS)
async def get_platform_ai_models(session: AsyncSession = Depends(get_session)):
    """
    Fetch the model list from ZAPRO.SU using the stored shared key; requires a system-tenant
    owner/admin. The connection need not be enabled. This is a live provider request, not a
    static model catalog. Missing/invalid configuration returns 422, credential-store errors 503
    and provider failures 502 with detail.code.
    """
    try:
        return {"items": await PlatformAIConnectionService.models(session)}
    except ZaprosuError as exc:
        _raise_safe(exc)


@router.post("/test", response_model=InferenceTest, operation_id=operation_ids.TEST_PLATFORM_AI_INFERENCE)
async def test_platform_ai(session: AsyncSession = Depends(get_session)):
    """
    Send a small live inference request to the selected ZAPRO.SU model using shared platform
    credentials, even if the connection is disabled. Requires a system-tenant owner/admin.
    Returns ok, model and reported token usage; the call may consume provider quota and repeats
    perform inference again. Missing model/configuration returns 422, unreadable credentials 503
    and provider failure 502 with detail.code. Does not enable the connection.
    """
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
    """
    Read effective shared DeepSeek configuration without returning its key; requires a
    system-tenant owner/admin. source=settings means a database record controls the connection,
    including an explicitly deleted/disabled record. Environment fallback applies only while no
    settings record exists. environment_key_available reports availability, not that the
    environment key is currently used; no provider call is made.
    """
    return DeepSeekConnectionService.public(await DeepSeekConnectionService.get(session))


@router.put("/deepseek", response_model=DeepseekConnectionStatus, operation_id=operation_ids.PUT_DEEPSEEK_CONNECTION)
async def put_deepseek_connection(payload: DeepseekConnectionUpdate, session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_system_owner_access)):
    """
    Save shared DeepSeek credentials/enabled state for a system-tenant owner/admin. A nonblank
    key replaces encrypted credentials; otherwise an existing key is retained. On the first
    save, an available environment key is copied into settings, after which there is no
    automatic environment fallback. Enabling without a key returns 422; credential-store errors
    return 503 with detail.code. Returns public state without testing provider access or a
    replay receipt.
    """
    try:
        result = await DeepSeekConnectionService.save(session, key=payload.key, enabled=payload.enabled)
    except DeepSeekCredentialError as exc:
        _raise_deepseek_safe(exc)
    logger.info("PLATFORM_AI_SETTINGS provider=deepseek actor=%s action=save key_replaced=%s enabled=%s", auth.username, bool((payload.key or "").strip()), result["enabled"])
    return result


@router.delete("/deepseek", response_model=DeepseekConnectionStatus, operation_id=operation_ids.DELETE_DEEPSEEK_CONNECTION)
async def delete_deepseek_connection(session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_system_owner_access)):
    """
    Clear stored DeepSeek credentials and explicitly disable the shared connection; requires a
    system-tenant owner/admin. Keeps a settings record so an environment key does not silently
    reactivate the connection. Repeating leaves it disabled. Returns public state without
    revoking the provider-side key or calling the provider.
    """
    result = await DeepSeekConnectionService.delete(session)
    logger.info("PLATFORM_AI_SETTINGS provider=deepseek actor=%s action=delete", auth.username)
    return result


@router.post("/deepseek/import-environment", response_model=DeepseekConnectionStatus, operation_id=operation_ids.IMPORT_DEEPSEEK_ENVIRONMENT_KEY)
async def import_deepseek_environment_key(session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_system_owner_access)):
    """
    Copy the available environment DeepSeek key into encrypted settings and enable the shared
    connection; requires a system-tenant owner/admin. Existing configured settings return 409
    already_configured, including a repeat after successful import; missing environment key
    returns 422 and credential-store errors 503. Returns public state, never the key, and does
    not verify provider inference.
    """
    try:
        result = await DeepSeekConnectionService.import_environment(session)
    except DeepSeekCredentialError as exc:
        _raise_deepseek_safe(exc)
    logger.info("PLATFORM_AI_SETTINGS provider=deepseek actor=%s action=import_environment", auth.username)
    return result


@router.post("/deepseek/test", response_model=DeepseekConnectionTest, operation_id=operation_ids.TEST_DEEPSEEK_CONNECTION)
async def test_deepseek_connection(session: AsyncSession = Depends(get_session)):
    """
    Send a small live JSON inference request with the effective shared DeepSeek key, even when
    saved settings are disabled. Requires a system-tenant owner/admin; an explicit deletion
    still suppresses environment fallback. Returns ok without enabling or updating settings.
    Repeats consume another provider request. Missing configuration returns 422, unreadable
    credentials 503 and provider/invalid-response failures 502 with detail.code.
    """
    try:
        return await DeepSeekConnectionService.test(session)
    except (DeepSeekCredentialError, DefectActAIProviderError) as exc:
        _raise_deepseek_safe(exc)
