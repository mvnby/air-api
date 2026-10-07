from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.manager_storefronts import ManagerStorefrontListResponse
from core.database import get_session
from core.auth_cookie import clear_auth_cookie
from core.security import AuthenticatedUser, require_manager_access
from routers.manager_operation_ids import (
    CHANGE_MANAGER_ACCOUNT_PASSWORD,
    LIST_MANAGER_STOREFRONTS,
    READ_USER_ME,
)
from schemas import ManagerAuthStatusResponse, ManagerPasswordChangePayload
from services.manager_capability_service import ManagerCapabilityService
from services.manager_storefront_selector_service import ManagerStorefrontSelector
from services.manager_account_credential_service import (
    ManagerAccountCredentialError,
    ManagerAccountCredentialService,
)


router = APIRouter(prefix="/api/manager", tags=["manager"])


@router.get("/me", response_model=ManagerAuthStatusResponse, operation_id=READ_USER_ME)
async def check_auth_status(auth: AuthenticatedUser = Depends(require_manager_access)):
    """
    Read the authenticated Manager identity, live tenant/storefront context and UI capabilities.
    Includes password-change eligibility, mandatory-password-change and demo-read-only flags.
    Does not issue or refresh a token. A valid authentication identity still needs Manager
    access and tenant/storefront context; insufficient access returns 403. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    return {
        "username": auth.username,
        "status": "authenticated",
        "staff_user_id": auth.staff_user_id,
        "role": auth.role,
        "display_name": auth.display_name,
        "auth_source": auth.auth_source,
        "tenant_id": auth.tenant_id,
        "storefront_id": auth.storefront_id,
        "tenant_membership_id": auth.tenant_membership_id,
        "is_system_tenant": auth.is_system_tenant,
        "capabilities": ManagerCapabilityService.for_auth(auth),
        "can_change_password": auth.can_change_password,
        "must_change_password": auth.must_change_password,
        "demo_read_only": auth.demo_read_only,
    }


@router.post(
    "/account/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id=CHANGE_MANAGER_ACCOUNT_PASSWORD,
)
async def change_account_password(
    payload: ManagerPasswordChangePayload,
    response: Response,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> None:
    """
    Change the current staff account password using its current password and record the
    credential change. Requires Manager access and self-service password eligibility;
    unavailable self-service returns 409 with detail.code=self_service_unavailable. Credential
    validation failures return 400 with code/message. Success is 204, increments the account
    auth version and clears the authentication cookie; sign in again. This command has no replay
    receipt, and the old password cannot be reused for a retry.
    """
    if auth.staff_user_id is None or not auth.can_change_password:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "self_service_unavailable",
                "message": "Для этой учётной записи самостоятельная смена пароля недоступна",
            },
        )
    try:
        await ManagerAccountCredentialService.change_password(
            session,
            staff_user_id=auth.staff_user_id,
            actor_username=auth.username,
            tenant_scope=auth.tenant_scope(),
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
    except ManagerAccountCredentialError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    clear_auth_cookie(response)


@router.get(
    "/storefronts",
    response_model=ManagerStorefrontListResponse,
    operation_id=LIST_MANAGER_STOREFRONTS,
)
async def list_manager_storefronts(
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    """
    List active storefronts belonging to the authenticated Manager's current tenant, including
    display metadata and is_current/is_default markers. This read does not switch storefront or
    issue credentials. The requested storefront is resolved within the same tenant by the
    Manager authentication contract; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    return await ManagerStorefrontSelector.list_available(
        session,
        tenant_scope=auth.tenant_scope(),
    )
