"""Platform-owner administration of explicit catalog permissions."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.manager_access import ManagerAccessItem, ManagerAccessList, ManagerAccessUpdate
from core.database import get_session
from core.security import AuthenticatedUser, require_system_owner_access
from routers.manager_operation_ids import LIST_MANAGER_ACCESS, UPDATE_MANAGER_ACCESS
from services.manager_access_service import ManagerAccessConflict, ManagerAccessService

router = APIRouter(prefix="/api/manager/platform/access", tags=["manager-access"])


@router.get("", response_model=ManagerAccessList, operation_id=LIST_MANAGER_ACCESS)
async def list_manager_access(
    page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=100),
    search: str | None = Query(None, max_length=200),
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_system_owner_access),
):
    """List company memberships and delegated catalog permissions for the platform owner.

    Read-only, paginated directory across companies; includes names, roles and status,
    never credentials or order data. Company owners/admins receive 403.
    """
    return await ManagerAccessService.list(session, page=page, limit=limit, search=search)


@router.patch("/{membership_id}", response_model=ManagerAccessItem, operation_id=UPDATE_MANAGER_ACCESS)
async def update_manager_access(
    membership_id: int, payload: ManagerAccessUpdate,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_system_owner_access),
):
    """Replace explicit catalog edit/delete grants for one company membership.

    Only the platform owner may delegate or revoke; no platform-owner grant is accepted.
    Live membership/identity status still applies on every use. Changes are audited.
    Requires expected_updated_at; concurrent changes return 409, missing membership 404.
    Re-read before retrying a stale request. An unchanged current request is a no-op.
    """
    try:
        result = await ManagerAccessService.update(session, membership_id=membership_id, payload=payload, actor=auth)
    except ManagerAccessConflict as exc:
        await session.rollback()
        raise HTTPException(409, str(exc)) from exc
    if result is None:
        raise HTTPException(404, "Участие сотрудника в компании не найдено")
    return result
