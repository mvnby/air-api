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
from routers.manager_permission_policy import ManagerPermissionRoute

router = APIRouter(
    prefix="/api/manager/tags",
    tags=["manager tags"],
    route_class=ManagerPermissionRoute,
)

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
    Read all shared tag groups with their tags; no pagination is accepted. This endpoint
    does not filter by authenticated storefront.

    Access and scope: Manager access is required; this reads the shared platform catalog,
    not tenant-owned copies. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
    Create a shared tag group, deriving slug from title when omitted. Duplicate slug returns
    400. POST has no idempotency receipt; this creates dictionary state rather than
    assigning product tags.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
    Update submitted tag-group fields. Missing group returns 404; a slug used by another
    group returns 400. This edits the shared dictionary, leaving product-tag associations
    attached to their tag IDs.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
    Permanently delete an empty shared tag group. Missing group returns 404, including after
    deletion; any remaining tag blocks deletion with 400. Remove/reassign tags first.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
    Create a tag in an existing shared group, deriving slug from title when omitted. Missing
    group returns 404; duplicate slug returns 400. This does not assign the tag to products;
    POST has no idempotency receipt.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
    Update submitted tag fields. Missing tag returns 404; conflicting slug returns 400.
    Product links continue to refer to the same tag ID; editing this shared tag affects all
    linked products.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
    Permanently delete the tag and its product-tag links. Missing tag returns 404, including
    on a repeat after deletion. This removes the shared label rather than just removing it
    from one product.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    await TagService.delete_tag(session=session, tag_id=tag_id)
    return {"message": "Тег успешно удален"}
