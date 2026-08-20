from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from models import StaffUser, TenantMembership
from services.staff_user_service import StaffUserService
from services.legacy_owner_auth_guard import LegacyOwnerAuthGuard
from services.legacy_owner_auth_state_service import (
    LegacyOwnerAuthStateUnavailableError,
)
from services.legacy_owner_managed_identity_service import (
    LegacyOwnerManagedIdentityService,
)
from services.tenant_scope_service import (
    SystemTenantScopeResolver,
    TenantScopeResolutionError,
)


@dataclass
class BotAccessContext:
    telegram_id: int
    is_staff: bool = False
    display_name: str = ""
    primary_role: str = ""
    roles: list[str] = field(default_factory=list)
    legacy_installer_id: Optional[int] = None

    @property
    def is_manager(self) -> bool:
        return self.primary_role in {
            StaffUserService.ROLE_OWNER,
            StaffUserService.ROLE_ADMIN,
            StaffUserService.ROLE_MANAGER,
        }

    @property
    def is_executor(self) -> bool:
        return bool(self.legacy_installer_id) or any(
            role in StaffUserService.EXECUTOR_ROLES for role in self.roles
        )


class BotAccessService:
    @staticmethod
    async def get_context(
        session: AsyncSession,
        telegram_id: int | str | None,
    ) -> BotAccessContext:
        try:
            normalized_telegram_id = int(telegram_id) if telegram_id is not None else 0
        except (TypeError, ValueError):
            normalized_telegram_id = 0

        context = BotAccessContext(telegram_id=normalized_telegram_id)
        if not normalized_telegram_id:
            return context

        user = (
            await session.execute(
                select(StaffUser)
                .where(StaffUser.telegram_id == normalized_telegram_id)
                .order_by(StaffUser.id.asc())
            )
        ).scalars().first()
        if user is not None:
            if not StaffUserService.is_active(user):
                return context
            try:
                legacy_owner_state = await LegacyOwnerAuthGuard.state(session)
            except LegacyOwnerAuthStateUnavailableError:
                return context
            is_managed_identity = (
                LegacyOwnerManagedIdentityService.is_bound(
                    legacy_owner_state,
                    staff_user_id=int(user.id or 0),
                )
                or LegacyOwnerAuthGuard.configured_username_matches(
                    str(user.username or "")
                )
            )
            if is_managed_identity:
                try:
                    legacy_owner_state = await LegacyOwnerAuthGuard.state(
                        session,
                        for_share=True,
                    )
                except LegacyOwnerAuthStateUnavailableError:
                    return context
            if not LegacyOwnerAuthGuard.allows_staff_identity(
                legacy_owner_state,
                staff_user_id=int(user.id or 0),
                username=str(user.username or ""),
            ):
                return context
            try:
                tenant_scope = await SystemTenantScopeResolver.resolve(session)
            except TenantScopeResolutionError:
                return context
            memberships = list((
                await session.execute(
                    select(TenantMembership).where(
                        TenantMembership.staff_user_id == int(user.id or 0),
                    )
                )
            ).scalars().all())
            membership = next(
                (
                    item
                    for item in memberships
                    if item.tenant_id == tenant_scope.tenant_id
                    and item.status == "active"
                ),
                None,
            )
            if membership is None:
                return context
            is_bound_owner = (
                legacy_owner_state.owner_staff_user_id is not None
                and int(legacy_owner_state.owner_staff_user_id) == int(user.id or 0)
            )
            if is_bound_owner and not await LegacyOwnerManagedIdentityService.exact_bound_staff_identity_allowed(
                session,
                state=legacy_owner_state,
                user=user,
            ):
                return context
            roles = StaffUserService.normalize_roles(user.roles)
            primary_role = StaffUserService.normalize_primary_role(
                membership.role
            )
            if primary_role not in roles:
                roles.append(primary_role)
            return BotAccessContext(
                telegram_id=normalized_telegram_id,
                is_staff=True,
                display_name=user.display_name,
                primary_role=primary_role,
                roles=roles,
                legacy_installer_id=user.legacy_installer_id,
            )

        if settings.is_admin_user(normalized_telegram_id):
            return BotAccessContext(
                telegram_id=normalized_telegram_id,
                is_staff=True,
                display_name="Администратор",
                primary_role=StaffUserService.ROLE_OWNER,
                roles=[StaffUserService.ROLE_OWNER],
            )

        return context
