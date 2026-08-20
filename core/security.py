"""JWT and cookie authentication helpers for protected API endpoints."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_session
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

    def tenant_scope(self) -> TenantScope:
        if not self.tenant_id or not self.storefront_id:
            raise ManagerTenantAccessResolutionError(
                "Authenticated user has no tenant scope"
            )
        return TenantScope(
            tenant_id=self.tenant_id,
            storefront_id=self.storefront_id,
            is_system=self.is_system_tenant,
        )


MANAGER_ACCESS_ROLES = frozenset({"owner", "admin", "manager"})
OWNER_ACCESS_ROLES = frozenset({"owner", "admin"})


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


async def get_current_auth_context(
    request: Request,
    token: Optional[str] = Depends(reusable_oauth2),
    session: AsyncSession = Depends(get_session),
) -> AuthenticatedUser:
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
            staff_user = await StaffUserService.get_by_id(session, int(staff_user_id))
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
            try:
                access = await ManagerTenantAccessResolver.resolve(
                    session,
                    staff_user_id=int(staff_user.id or 0),
                )
            except ManagerTenantAccessResolutionError as exc:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Active tenant membership required",
                ) from exc
            tenant_scope = await _resolve_requested_manager_storefront(
                session,
                request,
                access.tenant_scope,
            )
            return AuthenticatedUser(
                username=username,
                staff_user_id=int(staff_user.id or 0),
                role=access.role,
                display_name=staff_user.display_name,
                auth_source=auth_source,
                tenant_id=tenant_scope.tenant_id,
                storefront_id=tenant_scope.storefront_id,
                tenant_membership_id=access.membership_id,
                is_system_tenant=tenant_scope.is_system,
                auth_version=token_auth_version,
                must_change_password=bool(staff_user.must_change_password),
                can_change_password=bool(staff_user.password_hash),
            )

        if not LegacyOwnerAuthGuard.configured_username_matches(username):
             raise HTTPException(status_code=401, detail="Invalid user")

        legacy_owner_state = await LegacyOwnerAuthGuard.state(session)
        if not LegacyOwnerAuthGuard.allows_legacy_token(
            legacy_owner_state,
            token_version=payload.get("legacy_auth_version"),
        ):
            raise HTTPException(status_code=401, detail="Invalid user")

        tenant_scope = await SystemTenantScopeResolver.resolve(session)
        tenant_scope = await _resolve_requested_manager_storefront(
            session,
            request,
            tenant_scope,
        )
        return AuthenticatedUser(
            username=username,
            auth_source="legacy",
            role="owner",
            tenant_id=tenant_scope.tenant_id,
            storefront_id=tenant_scope.storefront_id,
            is_system_tenant=tenant_scope.is_system,
            auth_version=int(legacy_owner_state.legacy_token_version),
        )

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")


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
    auth: AuthenticatedUser = Depends(require_owner_access),
) -> AuthenticatedUser:
    """Restrict platform infrastructure to system-tenant owners/admins."""
    if not auth.is_system_tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System tenant owner access required",
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
) -> TenantScope:
    """Keep global platform surfaces unavailable to white-label tenants."""
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
