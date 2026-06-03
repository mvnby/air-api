import logging
import json
from typing import Iterable, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from models import Installer, StaffUser

logger = logging.getLogger(__name__)


class StaffUserService:
    ROLE_OWNER = "owner"
    ROLE_ADMIN = "admin"
    ROLE_MANAGER = "manager"
    ROLE_INSTALLER = "installer"
    ROLE_MAINTENANCE = "maintenance"
    ROLE_REPAIR = "repair"
    # Extra legacy-compatible executor role for the current manager measurer_id flow;
    # this does not replace the issue-defined maintenance/repair roles.
    ROLE_MEASURER = "measurer"

    STATUS_ACTIVE = "active"
    STATUS_INACTIVE = "inactive"
    STATUS_BLOCKED = "blocked"

    ROLES = {
        ROLE_OWNER,
        ROLE_ADMIN,
        ROLE_MANAGER,
        ROLE_INSTALLER,
        ROLE_MAINTENANCE,
        ROLE_REPAIR,
        ROLE_MEASURER,
    }
    OWNER_ADMIN_ROLES = {ROLE_OWNER, ROLE_ADMIN}
    MANAGEMENT_ROLES = {ROLE_OWNER, ROLE_ADMIN, ROLE_MANAGER}
    EXECUTOR_ROLES = {ROLE_INSTALLER, ROLE_MAINTENANCE, ROLE_REPAIR, ROLE_MEASURER}
    STATUSES = {STATUS_ACTIVE, STATUS_INACTIVE, STATUS_BLOCKED}

    @classmethod
    def normalize_role(cls, role: str) -> str:
        return str(role or "").strip().lower()

    @classmethod
    def normalize_roles(cls, roles: Iterable[str] | None) -> list[str]:
        if isinstance(roles, str):
            try:
                parsed = json.loads(roles)
            except json.JSONDecodeError:
                parsed = [roles]
            roles = parsed if isinstance(parsed, list) else [roles]

        normalized: list[str] = []
        seen: set[str] = set()
        for role in roles or []:
            value = cls.normalize_role(role)
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

    @classmethod
    def normalize_status(cls, status: str | None) -> str:
        value = str(status or "").strip().lower()
        return value if value in cls.STATUSES else cls.STATUS_ACTIVE

    @classmethod
    def has_role(cls, staff_user: StaffUser, role: str) -> bool:
        return cls.normalize_role(role) in cls.normalize_roles(getattr(staff_user, "roles", []))

    @classmethod
    def has_any_role(cls, staff_user: StaffUser, roles: Iterable[str]) -> bool:
        staff_roles = set(cls.normalize_roles(getattr(staff_user, "roles", [])))
        return any(cls.normalize_role(role) in staff_roles for role in roles)

    @classmethod
    def is_active(cls, staff_user: StaffUser) -> bool:
        return cls.normalize_status(getattr(staff_user, "status", None)) == cls.STATUS_ACTIVE

    @classmethod
    def can_receive_admin_notifications(cls, staff_user: StaffUser) -> bool:
        return (
            cls.is_active(staff_user)
            and bool(getattr(staff_user, "telegram_id", None))
            and cls.has_any_role(staff_user, cls.OWNER_ADMIN_ROLES)
        )

    @classmethod
    def can_use_bot_admin(cls, staff_user: StaffUser) -> bool:
        return cls.can_receive_admin_notifications(staff_user)

    @classmethod
    def can_be_executor(cls, staff_user: StaffUser, role: str) -> bool:
        return cls.is_active(staff_user) and cls.has_role(staff_user, role)

    @classmethod
    def can_be_any_executor(cls, staff_user: StaffUser) -> bool:
        return cls.is_active(staff_user) and cls.has_any_role(staff_user, cls.EXECUTOR_ROLES)

    @classmethod
    async def find_active_executors_by_role(
        cls,
        session: AsyncSession,
        role: str,
        *,
        search: Optional[str] = None,
        limit: int = 100,
    ) -> list[StaffUser]:
        stmt = select(StaffUser).where(StaffUser.status == cls.STATUS_ACTIVE).order_by(StaffUser.display_name.asc())
        result = await session.execute(stmt)
        users = list(result.scalars().all())

        search_value = str(search or "").strip().casefold()
        filtered: list[StaffUser] = []
        for user in users:
            if not cls.can_be_executor(user, role):
                continue
            if search_value and search_value not in str(user.display_name or "").casefold():
                continue
            filtered.append(user)
            if len(filtered) >= limit:
                break
        return filtered

    @classmethod
    async def get_active_owner_admin_telegram_recipient_ids(cls, session: AsyncSession) -> list[int]:
        try:
            stmt = (
                select(StaffUser)
                .where(StaffUser.status == cls.STATUS_ACTIVE)
                .where(StaffUser.telegram_id.is_not(None))
                .order_by(StaffUser.id.asc())
            )
            result = await session.execute(stmt)
            users = list(result.scalars().all())
        except Exception:
            logger.debug("STAFF_RECIPIENTS_DB_LOOKUP_FAILED using legacy ADMIN_IDS fallback", exc_info=True)
            return settings.admin_list

        recipient_ids: list[int] = []
        seen: set[int] = set()
        for user in users:
            if not cls.can_receive_admin_notifications(user):
                continue
            telegram_id = int(user.telegram_id)
            if telegram_id in seen:
                continue
            seen.add(telegram_id)
            recipient_ids.append(telegram_id)

        return recipient_ids or settings.admin_list

    @classmethod
    async def is_active_owner_admin_telegram_user(
        cls,
        session: AsyncSession,
        telegram_id: int | str | None,
    ) -> bool:
        if telegram_id is None:
            return False

        try:
            normalized_telegram_id = int(telegram_id)
        except (TypeError, ValueError):
            return False

        try:
            result = await session.execute(
                select(StaffUser)
                .where(StaffUser.telegram_id == normalized_telegram_id)
                .order_by(StaffUser.id.asc())
            )
            users = list(result.scalars().all())
        except Exception:
            logger.debug("STAFF_ADMIN_CHECK_DB_LOOKUP_FAILED using legacy ADMIN_IDS fallback", exc_info=True)
            return settings.is_admin_user(normalized_telegram_id)

        if not users:
            return settings.is_admin_user(normalized_telegram_id)

        return any(cls.can_use_bot_admin(user) for user in users)

    @classmethod
    async def get_active_executor_telegram_id_for_legacy_installer(
        cls,
        session: AsyncSession,
        installer: Installer,
    ) -> int | None:
        if installer.id is not None:
            staff_user = await cls.get_by_legacy_installer_id(session, int(installer.id))
            if staff_user is not None:
                if not cls.can_be_any_executor(staff_user) or not staff_user.telegram_id:
                    return None
                return int(staff_user.telegram_id)

        if not installer.is_active or not installer.telegram_id:
            return None
        return int(installer.telegram_id)

    @classmethod
    async def get_by_legacy_installer_id(
        cls,
        session: AsyncSession,
        installer_id: int,
    ) -> StaffUser | None:
        result = await session.execute(
            select(StaffUser).where(StaffUser.legacy_installer_id == installer_id)
        )
        return result.scalar_one_or_none()

    @classmethod
    async def ensure_for_installer(
        cls,
        session: AsyncSession,
        installer: Installer,
    ) -> StaffUser:
        if installer.id is None:
            await session.flush()

        staff_user = await cls.get_by_legacy_installer_id(session, int(installer.id))
        if not staff_user:
            staff_user = StaffUser(
                display_name=installer.name,
                status=cls.STATUS_ACTIVE if installer.is_active else cls.STATUS_INACTIVE,
                roles=[cls.ROLE_INSTALLER],
                telegram_id=installer.telegram_id,
                legacy_installer_id=installer.id,
                default_rate=installer.default_rate,
            )
            session.add(staff_user)
            await session.flush()
            return staff_user

        staff_user.display_name = installer.name
        staff_user.default_rate = installer.default_rate
        staff_user.telegram_id = installer.telegram_id
        roles = cls.normalize_roles(staff_user.roles)
        if cls.ROLE_INSTALLER not in roles:
            roles.append(cls.ROLE_INSTALLER)
        staff_user.roles = roles
        session.add(staff_user)
        await session.flush()
        return staff_user

    @classmethod
    async def set_installer_active_status(
        cls,
        session: AsyncSession,
        installer: Installer,
        is_active: bool,
    ) -> StaffUser:
        staff_user = await cls.ensure_for_installer(session, installer)
        staff_user.status = cls.STATUS_ACTIVE if is_active else cls.STATUS_INACTIVE
        session.add(staff_user)
        await session.flush()
        return staff_user
