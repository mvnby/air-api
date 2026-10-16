"""Personal profile and authenticated, company-scoped photos."""

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, Query
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from api_contracts.manager_profile import ManagerOwnAvatarDelete, ManagerOwnProfileResponse, ManagerOwnProfileUpdate
from core.config import settings
from core.database import get_session
from core.security import (AuthenticatedUser, AuthenticatedIdentity, get_current_identity,
                           require_personal_workspace_access, resolve_identity_tenant_access)
from routers.manager_operation_ids import (
    MANAGER_DELETE_OWN_AVATAR, MANAGER_GET_OWN_PROFILE, MANAGER_READ_STAFF_AVATAR,
    MANAGER_UPDATE_OWN_PROFILE, MANAGER_UPLOAD_OWN_AVATAR,
)
from services.legacy_owner_managed_identity_service import LegacyOwnerManagedIdentityError
from services.manager_profile_service import ManagerProfileError, ManagerProfileService
from services.staff_avatar_service import (
    MAX_AVATAR_INPUT_BYTES, StaffAvatarError, StaffAvatarService, sanitize_staff_avatar,
)

router = APIRouter(prefix="/api/manager", tags=["manager-profile"])


def require_account_origin(request: Request, *, header: str) -> None:
    allowed = {str(value).rstrip("/") for value in settings.CORS_ORIGINS}
    allowed.add(f"{request.url.scheme}://{request.url.netloc}")
    origin = request.headers.get("origin")
    if (request.headers.get(header) != "1"
            or (origin and origin.rstrip("/") not in allowed)
            or request.headers.get("sec-fetch-site") == "cross-site"):
        raise HTTPException(403, detail={"code": "profile_csrf", "message": "Обновите страницу и повторите действие"})


def require_profile_origin(request: Request) -> None:
    require_account_origin(request, header="X-Kitlane-Profile")


@asynccontextmanager
async def profile_errors(session: AsyncSession):
    try:
        yield
    except (ManagerProfileError, LegacyOwnerManagedIdentityError) as exc:
        await session.rollback()
        raise HTTPException(
            getattr(exc, "status_code", 409), detail={"code": exc.code, "message": str(exc)},
        ) from exc


@router.get("/account/profile", response_model=ManagerOwnProfileResponse, operation_id=MANAGER_GET_OWN_PROFILE)
async def get_own_profile(
    session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_personal_workspace_access),
):
    """Read only the authenticated person's contact, avatar and Telegram settings."""
    async with profile_errors(session):
        return ManagerProfileService.response(await ManagerProfileService.read(session, auth=auth), auth=auth)


@router.patch("/account/profile", response_model=ManagerOwnProfileResponse, operation_id=MANAGER_UPDATE_OWN_PROFILE,
              dependencies=[Depends(require_profile_origin)])
async def update_own_profile(
    payload: ManagerOwnProfileUpdate, session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_personal_workspace_access),
):
    """Change whitelisted personal fields with an optimistic timestamp and atomic audit.

    Company roles, grants, credentials and Telegram bindings cannot be set here.
    Requires X-Kitlane-Profile: 1. A stale timestamp returns 409/profile_changed.
    """
    async with profile_errors(session):
        return await ManagerProfileService.update(session, auth=auth, payload=payload)


@router.post("/account/profile/avatar", response_model=ManagerOwnProfileResponse, operation_id=MANAGER_UPLOAD_OWN_AVATAR,
             dependencies=[Depends(require_profile_origin)])
async def upload_own_avatar(
    file: UploadFile = File(...), expected_updated_at: datetime = Form(...),
    session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_personal_workspace_access),
):
    """Replace your photo with a sanitized 256px WebP; JPEG/PNG/WebP up to 5 MiB.

    Requires X-Kitlane-Profile: 1 and the current profile timestamp. Image processing
    discards metadata, rejects animation and runs outside the async event loop.
    """
    try:
        content = await file.read(MAX_AVATAR_INPUT_BYTES + 1)
    finally:
        await file.close()
    try:
        photo = await run_in_threadpool(sanitize_staff_avatar, content)
    except StaffAvatarError as exc:
        raise HTTPException(400, detail={"code": "invalid_avatar", "message": str(exc)}) from exc
    async with profile_errors(session):
        return await ManagerProfileService.set_avatar(
            session, auth=auth, expected_updated_at=expected_updated_at, photo=photo,
        )


@router.delete("/account/profile/avatar", response_model=ManagerOwnProfileResponse, operation_id=MANAGER_DELETE_OWN_AVATAR,
               dependencies=[Depends(require_profile_origin)])
async def delete_own_avatar(
    payload: ManagerOwnAvatarDelete, session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_personal_workspace_access),
):
    """Remove your photo, checking the current timestamp and recording an audit event."""
    async with profile_errors(session):
        return await ManagerProfileService.set_avatar(
            session, auth=auth, expected_updated_at=payload.expected_updated_at, photo=None,
        )


@router.get("/staff/{staff_user_id}/avatar", operation_id=MANAGER_READ_STAFF_AVATAR,
            responses={200: {"content": {"image/webp": {}}}, 304: {}, 404: {}}, response_class=Response)
async def read_staff_avatar(
    staff_user_id: int, request: Request, tenant_id: int = Query(..., gt=0), session: AsyncSession = Depends(get_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
):
    """Read a coworker's photo after company access checks, including before a 304.

    Historical memberships retain photo visibility on old orders. Platform owners
    can read across companies. Photos are private and revalidated on every request.
    """
    access = await resolve_identity_tenant_access(session, identity, tenant_id=tenant_id)
    avatar = await StaffAvatarService.read(
        session, staff_user_id=staff_user_id, viewer_tenant_id=access.tenant_scope.tenant_id,
        is_platform_owner=identity.is_platform_owner,
    )
    if avatar is None:
        raise HTTPException(404, detail="Фотография не найдена")
    etag = f'"{avatar.content_hash}"'
    headers = {"ETag": etag, "Cache-Control": "private, no-cache", "Vary": "Cookie, Authorization",
               "X-Content-Type-Options": "nosniff"}
    if etag in [value.strip() for value in request.headers.get("if-none-match", "").split(",")]:
        return Response(status_code=304, headers=headers)
    return Response(content=avatar.content, media_type="image/webp", headers=headers)
