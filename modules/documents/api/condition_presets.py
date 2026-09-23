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
    rows = await ConditionPresetService.list(session, auth.tenant_scope())
    return ConditionPresetList(items=[ConditionPresetItem.model_validate(row, from_attributes=True) for row in rows])


@router.post("", response_model=ConditionPresetItem, operation_id=CREATE_MANAGER_DOCUMENT_CONDITION_PRESET)
async def create_preset(
    payload: ConditionPresetPayload,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> ConditionPresetItem:
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
