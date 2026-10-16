"""JWT and cookie authentication helpers for protected API endpoints."""
from dataclasses import dataclass, asdict
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_session
from core.demo_access import enforce_demo_read_only
from models.tenancy import TenantScope
from services.manager_tenant_access_service import (
    ManagerTenantAccessResolutionError,
    ManagerTenantAccessResolver,
)
from services.manager_storefront_selector_service import (
    MANAGER_STOREFRONT_HEADER,
    ManagerStorefrontSelectionError,
    ManagerStorefrontSelector,
)
from services.staff_user_service import StaffUserService
from services.legacy_owner_auth_guard import LegacyOwnerAuthGuard
from services.legacy_owner_managed_identity_service import LegacyOwnerManagedIdentityService
from services.tenant_scope_service import SystemTenantScopeResolver

# JWT CONFIG
# TODO: Move to settings in the future
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 1 week

# OAuth2 scheme for Swagger UI (TokenUrl should point to login endpoint)
reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl="/login/access-token",
    auto_error=False
)


@dataclass(frozen=True)
class AuthenticatedIdentity:
    username: str
    auth_source: str
    staff_user_id: int | None = None
    display_name: str | None = None
    auth_version: int | None = None
    must_change_password: bool = False
    can_change_password: bool = False
    is_platform_owner: bool = False


@dataclass(frozen=True)
class AuthenticatedUser:
    username: str
    auth_source: str
    staff_user_id: int | None = None
    role: str | None = None
    display_name: str | None = None
    tenant_id: int | None = None
    storefront_id: int | None = None
    tenant_membership_id: int | None = None
    is_system_tenant: bool = False
    auth_version: int | None = None
    must_change_password: bool = False
    can_change_password: bool = False
    demo_read_only: bool = False
    is_platform_owner: bool = False
    permissions: tuple[str, ...] = ()
    access_kind: str = "membership"

    def tenant_scope(self) -> TenantScope:
        if not self.tenant_id or not self.storefront_id:
            raise ManagerTenantAccessResolutionError(
                "Authenticated user has no tenant scope"
            )
        return TenantScope(
            tenant_id=self.tenant_id,
            storefront_id=self.storefront_id,
            is_system=self.is_system_tenant,
            demo_read_only=self.demo_read_only,
        )


MANAGER_ACCESS_ROLES = frozenset({"owner", "admin", "manager"})
OWNER_ACCESS_ROLES = frozenset({"owner", "admin"})
WORKSPACE_ACCESS_ROLES = MANAGER_ACCESS_ROLES | {"catalog_editor"}


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a new JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def _extract_token(request: Request, token: Optional[str]) -> str:
    token_to_validate = token
    if not token_to_validate and request:
        token_to_validate = request.cookies.get("access_token")
        if token_to_validate and token_to_validate.startswith("Bearer "):
            token_to_validate = token_to_validate[7:]

    if not token_to_validate:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token_to_validate


async def _resolve_requested_manager_storefront(
    session: AsyncSession,
    request: Request,
    base_scope: TenantScope,
) -> TenantScope:
    try:
        return await ManagerStorefrontSelector.resolve(
            session,
            base_scope=base_scope,
            requested_slug=request.headers.get(MANAGER_STOREFRONT_HEADER),
        )
    except ManagerStorefrontSelectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Storefront access denied",
        ) from exc


async def get_current_identity(
    request: Request,
    token: Optional[str] = Depends(reusable_oauth2),
    session: AsyncSession = Depends(get_session),
) -> AuthenticatedIdentity:
    """
    Unified Dependency for Authentication.
    Checks:
    1. Authorization Header (Bearer ...)
    2. Cookie (access_token)
    """
    token_to_validate = _extract_token(request, token)
        
    try:
        payload = jwt.decode(token_to_validate, settings.SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
             raise HTTPException(status_code=401, detail="Invalid token")

        auth_source = str(payload.get("auth_source") or "legacy")
        staff_user_id = payload.get("staff_user_id")
        if staff_user_id is not None:
            try:
                staff_user_id = int(staff_user_id)
            except (TypeError, ValueError):
                raise HTTPException(401, detail="Invalid user") from None
            staff_user = await StaffUserService.get_by_id(session, staff_user_id)
            if staff_user is None or not StaffUserService.is_active(staff_user):
                raise HTTPException(status_code=401, detail="Invalid user")
            try:
                token_auth_version = int(payload["auth_version"])
            except (KeyError, TypeError, ValueError) as exc:
                raise HTTPException(status_code=401, detail="Invalid credential version") from exc
            if token_auth_version != int(staff_user.auth_version):
                raise HTTPException(status_code=401, detail="Credential has changed")
            if username != staff_user.username and username != str(staff_user.telegram_id or ""):
                raise HTTPException(status_code=401, detail="Invalid user")
            legacy_owner_state = await LegacyOwnerAuthGuard.state(session)
            if not LegacyOwnerAuthGuard.allows_staff_identity(
                legacy_owner_state,
                staff_user_id=int(staff_user.id or 0),
                username=str(staff_user.username or ""),
            ):
                raise HTTPException(status_code=401, detail="Invalid user")
            if LegacyOwnerManagedIdentityService.is_bound(
                legacy_owner_state, staff_user_id=int(staff_user.id or 0),
            ) and not await LegacyOwnerManagedIdentityService.exact_bound_staff_identity_allowed(
                session, state=legacy_owner_state, user=staff_user,
            ):
                raise HTTPException(status_code=401, detail="Invalid owner profile")
            return AuthenticatedIdentity(
                username=username, staff_user_id=int(staff_user.id),
                display_name=staff_user.display_name, auth_source=auth_source,
                auth_version=token_auth_version, must_change_password=bool(staff_user.must_change_password),
                can_change_password=bool(staff_user.password_hash),
                is_platform_owner=LegacyOwnerAuthGuard.allows_bound_staff(
                    legacy_owner_state, staff_user_id=int(staff_user.id)
                ),
            )

        if not LegacyOwnerAuthGuard.configured_username_matches(username):
             raise HTTPException(status_code=401, detail="Invalid user")

        legacy_owner_state = await LegacyOwnerAuthGuard.state(session)
        if not LegacyOwnerAuthGuard.allows_legacy_token(
            legacy_owner_state,
            token_version=payload.get("legacy_auth_version"),
        ):
            raise HTTPException(status_code=401, detail="Invalid user")

        return AuthenticatedIdentity(
            username=username, auth_source="legacy",
            auth_version=int(legacy_owner_state.legacy_token_version), is_platform_owner=True,
        )

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")


MANAGER_TENANT_HEADER = "X-MVN-Manager-Tenant"


def requested_manager_tenant(value: str | None) -> int | None:
    if value is None:
        return None
    if not re.fullmatch(r"[1-9][0-9]{0,18}", value) or int(value) > 2**63 - 1:
        raise HTTPException(403, detail={"code": "company_access_denied"})
    return int(value)


async def resolve_identity_tenant_access(session, identity, *, tenant_id=None, personal=False):
    try:
        if identity.staff_user_id is None:
            if not identity.is_platform_owner:
                raise ManagerTenantAccessResolutionError("Staff identity required")
            scope = await SystemTenantScopeResolver.resolve(session)
            if personal or tenant_id is None or tenant_id == scope.tenant_id:
                from services.manager_tenant_access_service import ManagerTenantAccess
                return ManagerTenantAccess(None, "owner", scope)
        else:
            if personal:
                return await ManagerTenantAccessResolver.personal(session, staff_user_id=identity.staff_user_id)
            try:
                return await ManagerTenantAccessResolver.resolve(session, staff_user_id=identity.staff_user_id, tenant_id=tenant_id)
            except ManagerTenantAccessResolutionError:
                if not identity.is_platform_owner or tenant_id is None:
                    raise
        if identity.is_platform_owner and tenant_id is not None:
            return await ManagerTenantAccessResolver.platform_support(session, tenant_id=tenant_id)
        raise ManagerTenantAccessResolutionError("Active company required")
    except ManagerTenantAccessResolutionError as exc:
        code = "company_selection_required" if tenant_id is None and exc.code == "company_selection_required" else "company_access_denied"
        raise HTTPException(409 if code == "company_selection_required" else 403, detail={"code": code}) from exc


def scoped_identity(identity, access, scope):
    return AuthenticatedUser(
        **{**asdict(identity), "can_change_password": identity.can_change_password and not scope.demo_read_only},
        role=access.role, tenant_id=scope.tenant_id, storefront_id=scope.storefront_id,
        tenant_membership_id=access.membership_id, is_system_tenant=scope.is_system,
        demo_read_only=scope.demo_read_only, permissions=access.permissions, access_kind=access.access_kind,
    )


async def get_current_auth_context(
    request: Request, token: Optional[str] = Depends(reusable_oauth2), session: AsyncSession = Depends(get_session),
) -> AuthenticatedUser:
    identity = await get_current_identity(request, token, session)
    access = await resolve_identity_tenant_access(
        session, identity, tenant_id=requested_manager_tenant(request.headers.get(MANAGER_TENANT_HEADER)),
    )
    scope = await _resolve_requested_manager_storefront(session, request, access.tenant_scope)
    enforce_demo_read_only(request, demo_read_only=scope.demo_read_only)
    return scoped_identity(identity, access, scope)


async def get_current_platform_identity(
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> AuthenticatedIdentity:
    if not identity.is_platform_owner:
        raise HTTPException(403, detail="Platform owner access required")
    return identity


async def require_personal_workspace_access(
    request: Request, identity: AuthenticatedIdentity = Depends(get_current_identity),
    session: AsyncSession = Depends(get_session),
) -> AuthenticatedUser:
    access = await resolve_identity_tenant_access(session, identity, personal=True)
    enforce_demo_read_only(request, demo_read_only=access.tenant_scope.demo_read_only)
    return scoped_identity(identity, access, access.tenant_scope)


def _normalized_role(auth: AuthenticatedUser) -> str:
    return str(auth.role or "").strip().lower()


async def require_manager_access(
    auth: AuthenticatedUser = Depends(get_current_auth_context),
) -> AuthenticatedUser:
    if (
        _normalized_role(auth) not in MANAGER_ACCESS_ROLES
        or not auth.tenant_id
        or not auth.storefront_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager access required",
        )
    return auth


async def require_workspace_access(
    auth: AuthenticatedUser = Depends(get_current_auth_context),
) -> AuthenticatedUser:
    if (
        _normalized_role(auth) not in WORKSPACE_ACCESS_ROLES
        or not auth.tenant_id
        or not auth.storefront_id
    ):
        raise HTTPException(status_code=403, detail="Workspace access required")
    return auth


async def require_catalog_master_edit(
    auth: AuthenticatedUser = Depends(require_workspace_access),
) -> AuthenticatedUser:
    if not auth.is_platform_owner and "catalog.master.edit" not in auth.permissions:
        raise HTTPException(status_code=403, detail="Catalog editing access required")
    return auth


async def require_catalog_master_delete(
    auth: AuthenticatedUser = Depends(require_catalog_master_edit),
) -> AuthenticatedUser:
    if not auth.is_platform_owner and "catalog.master.delete" not in auth.permissions:
        raise HTTPException(status_code=403, detail="Catalog deletion access required")
    return auth


async def get_current_catalog_username(
    auth: AuthenticatedUser = Depends(require_workspace_access),
) -> str:
    return auth.username


async def require_owner_access(
    auth: AuthenticatedUser = Depends(get_current_auth_context),
) -> AuthenticatedUser:
    if (
        _normalized_role(auth) not in OWNER_ACCESS_ROLES
        or not auth.tenant_id
        or not auth.storefront_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner access required",
        )
    return auth


async def require_system_owner_access(
    auth: AuthenticatedUser = Depends(require_workspace_access),
) -> AuthenticatedUser:
    """Use the durable owner identity, never company membership as authority."""
    if not auth.is_platform_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform owner access required",
        )
    return auth


async def get_current_user(
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> str:
    return auth.username


async def get_current_manager_tenant_scope(
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> TenantScope:
    return auth.tenant_scope()


async def require_system_manager_tenant_scope(
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
    auth: AuthenticatedUser = Depends(require_system_owner_access),
) -> TenantScope:
    """Compatibility name for operator-only, system-company workflows."""
    if not tenant_scope.is_system:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System tenant access required",
        )
    return tenant_scope


# Alias for backward compatibility if needed, but we should refactor usages.
get_current_username = get_current_user


async def get_current_owner_username(
    auth: AuthenticatedUser = Depends(require_owner_access),
) -> str:
    return auth.username
