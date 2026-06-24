from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from models import StaffUser
from services.staff_user_service import StaffUserService


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

        result = await session.execute(
            select(StaffUser)
            .where(StaffUser.telegram_id == normalized_telegram_id)
            .order_by(StaffUser.id.asc())
        )
        user = result.scalars().first()
        if user:
            if not StaffUserService.is_active(user):
                return context
            roles = StaffUserService.normalize_roles(user.roles)
            primary_role = StaffUserService.primary_role(user)
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
