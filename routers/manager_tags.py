from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from schemas import (
    ManagerTagGroupCreatePayload,
    ManagerTagGroupUpdatePayload,
    ManagerTagCreatePayload,
    ManagerTagUpdatePayload,
    ManagerTagGroupResponse,
    ManagerTagOptionResponse
)
from services.tag_service import TagService

from routers.manager_operation_ids import (
    GET_MANAGER_TAG_GROUPS,
    CREATE_MANAGER_TAG_GROUP,
    UPDATE_MANAGER_TAG_GROUP,
    DELETE_MANAGER_TAG_GROUP,
    CREATE_MANAGER_TAG,
    UPDATE_MANAGER_TAG,
    DELETE_MANAGER_TAG,
)

router = APIRouter(prefix="/api/manager/tags", tags=["manager tags"])

@router.get(
    "/groups",
    response_model=List[ManagerTagGroupResponse],
    operation_id=GET_MANAGER_TAG_GROUPS,
)
async def get_tag_groups(
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """
    Get all tag groups with their tags.
    """
    return await TagService.get_tag_groups(session=session)


@router.post(
    "/groups",
    response_model=ManagerTagGroupResponse,
    operation_id=CREATE_MANAGER_TAG_GROUP,
)
async def create_tag_group(
    payload: ManagerTagGroupCreatePayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """
    Create a new tag group.
    """
    return await TagService.create_tag_group(session=session, payload=payload)


@router.put(
    "/groups/{group_id}",
    response_model=ManagerTagGroupResponse,
    operation_id=UPDATE_MANAGER_TAG_GROUP,
)
async def update_tag_group(
    group_id: int,
    payload: ManagerTagGroupUpdatePayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """
    Update an existing tag group.
    """
    return await TagService.update_tag_group(session=session, group_id=group_id, payload=payload)


@router.delete(
    "/groups/{group_id}",
    operation_id=DELETE_MANAGER_TAG_GROUP,
)
async def delete_tag_group(
    group_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """
    Delete a tag group. Restrained if the group has tags.
    """
    await TagService.delete_tag_group(session=session, group_id=group_id)
    return {"message": "Группа успешно удалена"}


@router.post(
    "",
    response_model=ManagerTagOptionResponse,
    operation_id=CREATE_MANAGER_TAG,
)
async def create_tag(
    payload: ManagerTagCreatePayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """
    Create a new tag in a group.
    """
    return await TagService.create_tag(session=session, payload=payload)


@router.put(
    "/{tag_id}",
    response_model=ManagerTagOptionResponse,
    operation_id=UPDATE_MANAGER_TAG,
)
async def update_tag(
    tag_id: int,
    payload: ManagerTagUpdatePayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """
    Update a tag.
    """
    return await TagService.update_tag(session=session, tag_id=tag_id, payload=payload)


@router.delete(
    "/{tag_id}",
    operation_id=DELETE_MANAGER_TAG,
)
async def delete_tag(
    tag_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """
    Delete a tag.
    """
    await TagService.delete_tag(session=session, tag_id=tag_id)
    return {"message": "Тег успешно удален"}
