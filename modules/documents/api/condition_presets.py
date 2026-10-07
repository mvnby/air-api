"""Shared condition chips for CRM documents."""

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.security import AuthenticatedUser, require_manager_access
from modules.documents.application.condition_presets import (
    ConditionPresetError,
    ConditionPresetNotFound,
    ConditionPresetService,
)
from routers.manager_operation_ids import (
    CREATE_MANAGER_DOCUMENT_CONDITION_PRESET,
    DELETE_MANAGER_DOCUMENT_CONDITION_PRESET,
    LIST_MANAGER_DOCUMENT_CONDITION_PRESETS,
)
from routers.manager_permission_policy import ManagerPermissionRoute


router = APIRouter(
    prefix="/api/manager/document-system/condition-presets",
    tags=["manager-document-system"],
    dependencies=[Depends(require_manager_access)],
    route_class=ManagerPermissionRoute,
)


class ConditionPresetPayload(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class ConditionPresetItem(BaseModel):
    id: int
    text: str


class ConditionPresetList(BaseModel):
    items: list[ConditionPresetItem]


@router.get("", response_model=ConditionPresetList, operation_id=LIST_MANAGER_DOCUMENT_CONDITION_PRESETS)
async def list_presets(
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> ConditionPresetList:
    """
    List up to 100 reusable document clauses in the current tenant, newest first. Reading
    does not apply a clause to an order or document.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    rows = await ConditionPresetService.list(session, auth.tenant_scope())
    return ConditionPresetList(items=[ConditionPresetItem.model_validate(row, from_attributes=True) for row in rows])


@router.post("", response_model=ConditionPresetItem, operation_id=CREATE_MANAGER_DOCUMENT_CONDITION_PRESET)
async def create_preset(
    payload: ConditionPresetPayload,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> ConditionPresetItem:
    """
    Save a reusable clause in the current tenant after trimming and case/whitespace
    normalization for duplicate detection. Invalid or duplicate text returns 409. Repeating
    this POST can conflict; it is not an idempotency-key replay.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        row = await ConditionPresetService.create(session, auth.tenant_scope(), payload.text)
    except ConditionPresetError as exc:
        raise manager_http_error(
            status_code=409,
            endpoint=CREATE_MANAGER_DOCUMENT_CONDITION_PRESET,
            error_code="document_condition_preset_invalid",
            message=str(exc),
        ) from exc
    return ConditionPresetItem.model_validate(row, from_attributes=True)


@router.delete("/{preset_id}", status_code=204, operation_id=DELETE_MANAGER_DOCUMENT_CONDITION_PRESET)
async def delete_preset(
    preset_id: int,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> Response:
    """
    Delete a clause in the current tenant, returning 204. Missing or foreign-tenant clause
    returns 404, including a repeat after deletion; existing document snapshots are not
    rewritten.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        await ConditionPresetService.delete(session, auth.tenant_scope(), preset_id)
    except ConditionPresetNotFound as exc:
        raise manager_http_error(
            status_code=404,
            endpoint=DELETE_MANAGER_DOCUMENT_CONDITION_PRESET,
            error_code="document_condition_preset_not_found",
            message=str(exc),
        ) from exc
    return Response(status_code=204)
