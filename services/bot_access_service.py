from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import StaffUser
from services.staff_user_service import StaffUserService
from services.legacy_owner_auth_guard import LegacyOwnerAuthGuard
from services.legacy_owner_auth_state_service import (
    LegacyOwnerAuthStateUnavailableError,
)
from services.legacy_owner_managed_identity_service import (
    LegacyOwnerManagedIdentityService,
)



@dataclass
class BotAccessContext:
    telegram_id: int
    is_staff: bool = False
    display_name: str = ""
    primary_role: str = ""
    roles: list[str] = field(default_factory=list)
    legacy_installer_id: Optional[int] = None
    is_platform_owner: bool = False
    permissions: tuple[str, ...] = ()
    selection: object | None = None
    staff_user_id: int | None = None
    selection_unavailable: bool = False

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
        *, ignore_selection: bool = False,
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
                .order_by(StaffUser.id.asc()).execution_options(populate_existing=True)
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
            from services.bot_staff_selection_service import BotStaffSelectionService
            selection = await BotStaffSelectionService.resolve(session, int(user.id), ignore_selection=ignore_selection)
            if selection is None:
                # Keep company selection recoverable without granting any CRM role.
                available = await BotStaffSelectionService.resolve(session, int(user.id), ignore_selection=True)
                return BotAccessContext(telegram_id=normalized_telegram_id, staff_user_id=int(user.id),
                                        display_name=user.display_name, selection=available,
                                        selection_unavailable=True)
            if not StaffUserService.is_active(user):
                return context
            issued = session.info.get("bot_selection")
            if issued is not None:
                if issued.staff_user_id != int(user.id) or (issued.tenant_id, issued.storefront_id, issued.context_version) != (selection.tenant_id, selection.storefront_id, selection.context_version):
                    from services.bot_staff_selection_service import context_changed
                    raise context_changed()
                if issued.role != selection.role or issued.permissions != selection.permissions:
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
            primary_role = StaffUserService.normalize_primary_role(selection.role)
            roles = [primary_role]
            # The old global executor assignment belongs exclusively to mvn/main.
            legacy_installer_id = user.legacy_installer_id if selection.canonical and primary_role in {"owner", "admin", "manager", "installer"} else None
            return BotAccessContext(
                telegram_id=normalized_telegram_id,
                is_staff=True,
                display_name=user.display_name,
                primary_role=primary_role,
                roles=roles,
                legacy_installer_id=legacy_installer_id,
                selection=selection,
                staff_user_id=int(user.id),
                is_platform_owner=LegacyOwnerAuthGuard.allows_bound_staff(
                    legacy_owner_state, staff_user_id=int(user.id or 0),
                ),
                permissions=selection.permissions,
            )

        return context
