"""Manual invitation links; no outbound messages or automatic account matching."""
from contextlib import asynccontextmanager
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from api_contracts.manager_invitations import (
    ManagerStaffInvitationCreate, ManagerStaffInvitationCreated, ManagerStaffInvitationList,
    StaffInvitationToken, StaffInvitationPreview, StaffInvitationAccept, StaffInvitationAccepted,
)
from core.database import get_session
from core.security import AuthenticatedUser, get_current_identity, reusable_oauth2, require_owner_access
from routers.manager_profile import require_account_origin
from routers.manager_operation_ids import (
    MANAGER_CREATE_STAFF_INVITATION, MANAGER_LIST_STAFF_INVITATIONS,
    MANAGER_REVOKE_STAFF_INVITATION,
)
from services.client_address_service import ClientAddressService
from services.credential_service import CredentialPolicyError
from services.login_throttle_service import LoginThrottleExceeded
from services.staff_access_policy import StaffAccessPolicyError
from services.staff_invitation_service import StaffInvitationError, StaffInvitationService
from services.staff_telegram_security import issue_staff_cookie

router = APIRouter(prefix="/api/manager/staff/invitations", tags=["manager-team"])
public_router = APIRouter(prefix="/api/account/invitations", tags=["account-invitations"])


def require_team_origin(request: Request):
    require_account_origin(request, header="X-Kitlane-Team")


@asynccontextmanager
async def invitation_errors(session):
    try:
        yield
    except LoginThrottleExceeded as exc:
        await session.rollback()
        raise HTTPException(429, detail={"code": "login_rate_limited"}, headers={"Retry-After": str(exc.retry_after_seconds)}) from None
    except (StaffInvitationError, StaffAccessPolicyError, CredentialPolicyError) as exc:
        await session.rollback()
        raise HTTPException(getattr(exc, "status_code", 400), detail={"code": exc.code, "message": str(exc)}) from None
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, detail={"code": "invitation_conflict", "message": "Данные уже изменились. Обновите страницу"}) from None


@router.post("", response_model=ManagerStaffInvitationCreated, operation_id=MANAGER_CREATE_STAFF_INVITATION, dependencies=[Depends(require_team_origin)])
async def create_invitation(payload: ManagerStaffInvitationCreate, session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_owner_access)):
    """Create a seven-day manual invitation. Requires X-Kitlane-Team:1 and approved Origin.

    Live owner/admin hierarchy determines assignable roles; platform support uses verified
    owner authority. Returns its bearer URL only once. No email is sent, no user is created
    and no catalog permission is granted. Legacy recovery identities without staff return403.
    """
    async with invitation_errors(session):
        return await StaffInvitationService.create(session, auth=auth, role=payload.role)


@router.get("", response_model=ManagerStaffInvitationList, operation_id=MANAGER_LIST_STAFF_INVITATIONS)
async def list_invitations(page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=100), session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_owner_access)):
    """List invitation status in the selected company; never returns tokens or password data."""
    return await StaffInvitationService.list(session, auth=auth, page=page, limit=limit)


@router.delete("/{invitation_id}", status_code=204, operation_id=MANAGER_REVOKE_STAFF_INVITATION, dependencies=[Depends(require_team_origin)])
async def revoke_invitation(invitation_id: int, session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_owner_access)):
    """Revoke a pending invitation with live hierarchy checks and an atomic audit receipt.

    Requires X-Kitlane-Team:1 and approved Origin. Accepted links cannot grant access again;
    revoking an already finished invitation does not change its existing membership.
    """
    async with invitation_errors(session):
        await StaffInvitationService.revoke(session, auth=auth, invitation_id=invitation_id)


@public_router.post("/preview", response_model=StaffInvitationPreview, operation_id="preview_staff_invitation")
async def preview_invitation(payload: StaffInvitationToken, session: AsyncSession = Depends(get_session)):
    """Preview company name, role and expiry from a bearer token carried in JSON, not a URL query.

    No account lookup or membership mutation occurs. Invalid, expired, used, revoked or
    unavailable-company invitations return404. Preview does not consume the token.
    """
    async with invitation_errors(session):
        return await StaffInvitationService.preview(session, token=payload.token)


@public_router.post("/accept", response_model=StaffInvitationAccepted, operation_id="accept_staff_invitation", dependencies=[Depends(require_team_origin)])
async def accept_invitation(payload: StaffInvitationAccept, request: Request, response: Response,
                            token: str | None = Depends(reusable_oauth2), session: AsyncSession = Depends(get_session)):
    """Accept once using an existing session, explicit account credentials, or a new strong password.

    Requires X-Kitlane-Team:1 and approved Origin. Password proof is rate limited. Live inviter
    authority is checked under locks; no email matching, password reset, existing-membership
    upgrade, catalog grant or blocked/merged account reactivation occurs. A returning inactive
    person can prove their existing password and join a new company while all old memberships
    stay disabled; auth_version increments. New/credential modes set a normal HttpOnly cookie.
    """
    async with invitation_errors(session):
        identity = await get_current_identity(request, token, session) if payload.mode == "existing" else None
        result, snapshot = await StaffInvitationService.accept(session, payload=payload, identity=identity,
                source=ClientAddressService.normalize(request.client.host if request.client else None))
        if payload.mode != "existing":
            issue_staff_cookie(response, snapshot, auth_source="staff_password")
        return result
