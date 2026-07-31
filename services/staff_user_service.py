import logging
import json
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from typing import Iterable, Optional
from urllib.parse import parse_qsl

import bcrypt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, func, or_

from core.config import settings
from models import Installer, StaffUser, TenantMembership
from models.tenancy import TenantScope
from schemas import ManagerStaffCreatePayload, ManagerStaffUpdatePayload, ManagerStaffResponse, ManagerStaffListResponse, Meta
from services.staff_tenant_membership_service import (
    StaffTenantMembershipService,
)

logger = logging.getLogger(__name__)


class StaffUserService:
    DISABLED_BOT_TOKEN_PLACEHOLDER = "0:disabled-bot-token"
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

    PRIMARY_ROLES = {ROLE_OWNER, ROLE_MANAGER, ROLE_INSTALLER}
    ROLES = PRIMARY_ROLES | {ROLE_ADMIN, ROLE_MAINTENANCE, ROLE_REPAIR, ROLE_MEASURER}
    OWNER_ADMIN_ROLES = {ROLE_OWNER, ROLE_MANAGER}
    MANAGEMENT_ROLES = {ROLE_OWNER, ROLE_ADMIN, ROLE_MANAGER}
    EXECUTOR_ROLES = {ROLE_INSTALLER, ROLE_MAINTENANCE, ROLE_REPAIR, ROLE_MEASURER}
    STATUSES = {STATUS_ACTIVE, STATUS_INACTIVE, STATUS_BLOCKED}

    @classmethod
    def normalize_role(cls, role: str) -> str:
        return str(role or "").strip().lower()

    @classmethod
    def normalize_primary_role(cls, role: str | None, roles: Iterable[str] | None = None) -> str:
        value = cls.normalize_role(role or "")
        if value == cls.ROLE_ADMIN:
            return cls.ROLE_OWNER
        if value in {cls.ROLE_OWNER, cls.ROLE_MANAGER}:
            return value

        legacy_roles = set(cls.normalize_roles(roles))
        if cls.ROLE_OWNER in legacy_roles or cls.ROLE_ADMIN in legacy_roles:
            return cls.ROLE_OWNER
        if cls.ROLE_MANAGER in legacy_roles:
            return cls.ROLE_MANAGER
        if value == cls.ROLE_INSTALLER:
            return cls.ROLE_INSTALLER
        return cls.ROLE_INSTALLER

    @classmethod
    def primary_role(cls, staff_user: StaffUser) -> str:
        return cls.normalize_primary_role(getattr(staff_user, "primary_role", None), getattr(staff_user, "roles", []))

    @classmethod
    def roles_for_primary(cls, primary_role: str, *, assignable_as_installer: bool = False) -> list[str]:
        normalized = cls.normalize_primary_role(primary_role)
        roles = [normalized]
        if assignable_as_installer and cls.ROLE_INSTALLER not in roles:
            roles.append(cls.ROLE_INSTALLER)
        return roles

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
            and cls.primary_role(staff_user) in cls.OWNER_ADMIN_ROLES
        )

    @classmethod
    def can_use_bot_admin(cls, staff_user: StaffUser) -> bool:
        return cls.can_receive_admin_notifications(staff_user)

    @classmethod
    def can_be_executor(cls, staff_user: StaffUser, role: str) -> bool:
        return (
            cls.is_active(staff_user)
            and getattr(staff_user, "legacy_installer_id", None) is not None
            and cls.has_role(staff_user, role)
        )

    @classmethod
    def can_be_any_executor(cls, staff_user: StaffUser) -> bool:
        return (
            cls.is_active(staff_user)
            and getattr(staff_user, "legacy_installer_id", None) is not None
            and cls.has_any_role(staff_user, cls.EXECUTOR_ROLES)
        )

    @staticmethod
    def normalize_username(username: str | None) -> str | None:
        value = str(username or "").strip().lower()
        return value or None

    @staticmethod
    def hash_password(password: str) -> str:
        value = str(password or "")
        if len(value) < 6:
            raise ValueError("Пароль должен быть не короче 6 символов")
        return bcrypt.hashpw(value.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify_password(password: str, password_hash: str | None) -> bool:
        if not password_hash:
            return False
        try:
            return bcrypt.checkpw(str(password or "").encode("utf-8"), password_hash.encode("utf-8"))
        except ValueError:
            return False

    @classmethod
    def _response(
        cls,
        user: StaffUser,
        *,
        membership: TenantMembership | None = None,
    ) -> ManagerStaffResponse:
        return ManagerStaffResponse(
            id=int(user.id or 0),
            display_name=user.display_name,
            status=(
                StaffTenantMembershipService.staff_status(membership.status)
                if membership is not None
                else cls.normalize_status(user.status)
            ),
            primary_role=(
                cls.normalize_primary_role(membership.role)
                if membership is not None
                else cls.primary_role(user)
            ),
            username=user.username,
            has_password=bool(user.password_hash),
            phone=user.phone,
            email=user.email,
            telegram_id=user.telegram_id,
            telegram_username=user.telegram_username,
            is_assignable_installer=user.legacy_installer_id is not None,
            legacy_installer_id=user.legacy_installer_id,
            default_rate=user.default_rate,
            created_at=user.created_at,
            updated_at=user.updated_at,
            last_login_at=user.last_login_at,
        )

    @classmethod
    async def authenticate_password(cls, session: AsyncSession, username: str, password: str) -> StaffUser | None:
        normalized_username = cls.normalize_username(username)
        if not normalized_username:
            return None

        result = await session.execute(select(StaffUser).where(StaffUser.username == normalized_username))
        user = result.scalar_one_or_none()
        if user is None or not cls.is_active(user):
            return None
        if not cls.verify_password(password, user.password_hash):
            return None

        user.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
        user.primary_role = cls.primary_role(user)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    @classmethod
    async def authenticate_telegram_login(
        cls,
        session: AsyncSession,
        payload: dict[str, str | int],
        *,
        max_age: timedelta = timedelta(minutes=10),
    ) -> StaffUser | None:
        if not cls.verify_telegram_login_payload(payload, max_age=max_age):
            return None

        telegram_id = payload.get("id")
        try:
            normalized_telegram_id = int(telegram_id)
        except (TypeError, ValueError):
            return None

        result = await session.execute(select(StaffUser).where(StaffUser.telegram_id == normalized_telegram_id))
        user = result.scalar_one_or_none()
        if user is None or not cls.is_active(user):
            return None

        username = str(payload.get("username") or "").strip() or None
        if username and user.telegram_username != username:
            user.telegram_username = username
        user.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
        user.primary_role = cls.primary_role(user)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    @staticmethod
    def _telegram_payload_items(payload: dict[str, str | int] | str) -> dict[str, str]:
        if isinstance(payload, str):
            return {key: value for key, value in parse_qsl(payload, keep_blank_values=True)}
        return {str(key): str(value) for key, value in payload.items() if value is not None}

    @classmethod
    def verify_telegram_login_payload(
        cls,
        payload: dict[str, str | int] | str,
        *,
        max_age: timedelta = timedelta(minutes=10),
    ) -> bool:
        bot_token = str(settings.BOT_TOKEN or "").strip()
        if not bot_token or bot_token == cls.DISABLED_BOT_TOKEN_PLACEHOLDER:
            return False

        values = cls._telegram_payload_items(payload)
        received_hash = values.pop("hash", "")
        if not received_hash:
            return False

        try:
            auth_date = datetime.fromtimestamp(int(values.get("auth_date", "0")), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            return False
        if datetime.now(timezone.utc) - auth_date > max_age:
            return False

        data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
        secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
        expected_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_hash, received_hash)

    @classmethod
    async def get_by_id(cls, session: AsyncSession, staff_user_id: int) -> StaffUser | None:
        return await session.get(StaffUser, staff_user_id)

    @classmethod
    async def list_staff(
        cls,
        session: AsyncSession,
        page: int = 1,
        limit: int = 100,
        search: Optional[str] = None,
        *,
        tenant_scope: TenantScope,
    ) -> ManagerStaffListResponse:
        stmt = (
            select(StaffUser, TenantMembership)
            .join(
                TenantMembership,
                TenantMembership.staff_user_id == StaffUser.id,
            )
            .where(TenantMembership.tenant_id == tenant_scope.tenant_id)
        )
        if search:
            query = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(StaffUser.display_name).like(query),
                    func.lower(StaffUser.username).like(query),
                    func.lower(StaffUser.email).like(query),
                    func.lower(StaffUser.phone).like(query),
                    func.lower(StaffUser.telegram_username).like(query),
                )
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_res = await session.execute(count_stmt)
        total = total_res.scalar() or 0

        result = await session.execute(
            stmt.order_by(StaffUser.display_name.asc()).offset((page - 1) * limit).limit(limit)
        )
        items = [
            cls._response(user, membership=membership)
            for user, membership in result.all()
        ]
        pages = (total + limit - 1) // limit if total > 0 else 1
        return ManagerStaffListResponse(items=items, meta=Meta(total=total, page=page, limit=limit, pages=pages))

    @classmethod
    async def create_staff(
        cls,
        session: AsyncSession,
        payload: ManagerStaffCreatePayload,
        *,
        tenant_scope: TenantScope,
    ) -> ManagerStaffResponse:
        username = cls.normalize_username(payload.username)
        primary_role = cls.normalize_primary_role(payload.primary_role)
        assignable = bool(payload.is_assignable_installer)
        display_name = payload.display_name.strip()
        if not display_name:
            raise ValueError("Имя сотрудника обязательно")
        staff_user = StaffUser(
            display_name=display_name,
            status=cls.normalize_status(payload.status),
            primary_role=primary_role,
            roles=cls.roles_for_primary(primary_role, assignable_as_installer=assignable),
            username=username,
            password_hash=cls.hash_password(payload.password) if payload.password else None,
            phone=payload.phone,
            email=payload.email,
            telegram_id=payload.telegram_id,
            telegram_username=payload.telegram_username,
            default_rate=payload.default_rate,
        )
        session.add(staff_user)
        await session.flush()
        membership = TenantMembership(
            tenant_id=tenant_scope.tenant_id,
            staff_user_id=int(staff_user.id or 0),
            role=primary_role,
            status=StaffTenantMembershipService.membership_status(
                staff_user.status
            ),
        )
        session.add(membership)
        await cls._sync_installer_link(session, staff_user, assignable)
        await session.commit()
        await session.refresh(staff_user)
        await session.refresh(membership)
        return cls._response(staff_user, membership=membership)

    @classmethod
    async def update_staff(
        cls,
        session: AsyncSession,
        staff_user_id: int,
        payload: ManagerStaffUpdatePayload,
        *,
        tenant_scope: TenantScope,
    ) -> ManagerStaffResponse | None:
        row = (
            await session.execute(
                select(StaffUser, TenantMembership)
                .join(
                    TenantMembership,
                    TenantMembership.staff_user_id == StaffUser.id,
                )
                .where(
                    StaffUser.id == staff_user_id,
                    TenantMembership.tenant_id == tenant_scope.tenant_id,
                )
                .with_for_update()
            )
        ).first()
        if row is None:
            return None
        staff_user, membership = row

        changed_fields = set(payload.model_fields_set)
        memberships = await StaffTenantMembershipService.list_for_staff(
            session,
            staff_user_id=staff_user_id,
            lock=True,
        )
        StaffTenantMembershipService.validate_shared_identity_update(
            changed_fields=changed_fields,
            membership_count=len(memberships),
            is_system_tenant=tenant_scope.is_system,
        )
        sync_global_profile = tenant_scope.is_system or len(memberships) == 1

        if "display_name" in changed_fields and payload.display_name is not None:
            display_name = payload.display_name.strip()
            if not display_name:
                raise ValueError("Имя сотрудника обязательно")
            staff_user.display_name = display_name
        if "status" in changed_fields:
            membership.status = StaffTenantMembershipService.membership_status(
                payload.status
            )
            StaffTenantMembershipService.touch(membership)
            staff_user.status = (
                StaffTenantMembershipService.aggregate_staff_status(
                    memberships
                )
            )
        if "primary_role" in changed_fields:
            membership.role = cls.normalize_primary_role(payload.primary_role)
            StaffTenantMembershipService.touch(membership)
            if sync_global_profile:
                staff_user.primary_role = membership.role
        else:
            staff_user.primary_role = cls.primary_role(staff_user)
        if "username" in changed_fields:
            staff_user.username = cls.normalize_username(payload.username)
        if payload.password:
            staff_user.password_hash = cls.hash_password(payload.password)
        if "phone" in changed_fields:
            staff_user.phone = payload.phone or None
        if "email" in changed_fields:
            staff_user.email = payload.email or None
        if "telegram_id" in changed_fields:
            staff_user.telegram_id = payload.telegram_id
        if "telegram_username" in changed_fields:
            staff_user.telegram_username = payload.telegram_username or None
        if "default_rate" in changed_fields:
            staff_user.default_rate = payload.default_rate

        assignable = (
            bool(payload.is_assignable_installer)
            if "is_assignable_installer" in changed_fields
            else staff_user.legacy_installer_id is not None
        )
        if sync_global_profile:
            staff_user.roles = cls.roles_for_primary(
                staff_user.primary_role,
                assignable_as_installer=assignable,
            )
        session.add(staff_user)
        session.add(membership)
        await session.flush()
        if sync_global_profile:
            await cls._sync_installer_link(session, staff_user, assignable)
        await session.commit()
        await session.refresh(staff_user)
        await session.refresh(membership)
        return cls._response(staff_user, membership=membership)

    @classmethod
    async def _sync_installer_link(
        cls,
        session: AsyncSession,
        staff_user: StaffUser,
        assignable: bool,
    ) -> None:
        if assignable:
            installer: Installer | None = None
            if staff_user.legacy_installer_id:
                installer = await session.get(Installer, staff_user.legacy_installer_id)
            if installer is None:
                installer = Installer(name=staff_user.display_name)
                session.add(installer)
                await session.flush()
                staff_user.legacy_installer_id = installer.id
            installer.name = staff_user.display_name
            installer.is_active = cls.is_active(staff_user)
            installer.default_rate = staff_user.default_rate
            installer.telegram_id = staff_user.telegram_id
            session.add(installer)
            session.add(staff_user)
            await session.flush()
            return

        if staff_user.legacy_installer_id:
            installer = await session.get(Installer, staff_user.legacy_installer_id)
            if installer is not None:
                installer.is_active = False
                session.add(installer)
        staff_user.legacy_installer_id = None
        session.add(staff_user)
        await session.flush()

    @classmethod
    async def find_active_executors_by_role(
        cls,
        session: AsyncSession,
        role: str,
        *,
        search: Optional[str] = None,
        limit: int = 100,
        tenant_scope: TenantScope,
    ) -> list[StaffUser]:
        stmt = (
            select(StaffUser)
            .join(
                TenantMembership,
                TenantMembership.staff_user_id == StaffUser.id,
            )
            .where(
                StaffUser.status == cls.STATUS_ACTIVE,
                TenantMembership.tenant_id == tenant_scope.tenant_id,
                TenantMembership.status == "active",
            )
            .order_by(StaffUser.display_name.asc())
        )
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
    async def get_active_owner_admin_telegram_recipient_ids(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> list[int]:
        try:
            stmt = (
                select(StaffUser, TenantMembership)
                .join(
                    TenantMembership,
                    TenantMembership.staff_user_id == StaffUser.id,
                )
                .where(
                    StaffUser.status == cls.STATUS_ACTIVE,
                    StaffUser.telegram_id.is_not(None),
                    TenantMembership.tenant_id == tenant_scope.tenant_id,
                    TenantMembership.status == "active",
                )
                .order_by(StaffUser.id.asc())
            )
            result = await session.execute(stmt)
            rows = list(result.all())
        except Exception:
            logger.debug(
                "STAFF_RECIPIENTS_DB_LOOKUP_FAILED tenant_id=%s",
                tenant_scope.tenant_id,
                exc_info=True,
            )
            return settings.admin_list if tenant_scope.is_system else []

        recipient_ids: list[int] = []
        seen: set[int] = set()
        for user, membership in rows:
            membership_role = cls.normalize_primary_role(membership.role)
            if membership_role not in cls.OWNER_ADMIN_ROLES:
                continue
            telegram_id = int(user.telegram_id)
            if telegram_id in seen:
                continue
            seen.add(telegram_id)
            recipient_ids.append(telegram_id)

        if recipient_ids:
            return recipient_ids
        return settings.admin_list if tenant_scope.is_system else []

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
        *,
        tenant_scope: TenantScope | None = None,
    ) -> StaffUser:
        if installer.id is None:
            await session.flush()

        staff_user = await cls.get_by_legacy_installer_id(session, int(installer.id))
        if not staff_user:
            staff_user = StaffUser(
                display_name=installer.name,
                status=cls.STATUS_ACTIVE if installer.is_active else cls.STATUS_INACTIVE,
                primary_role=cls.ROLE_INSTALLER,
                roles=[cls.ROLE_INSTALLER],
                telegram_id=installer.telegram_id,
                legacy_installer_id=installer.id,
                default_rate=installer.default_rate,
            )
            session.add(staff_user)
            await session.flush()
            if tenant_scope is not None:
                await StaffTenantMembershipService.ensure(
                    session,
                    tenant_id=tenant_scope.tenant_id,
                    staff_user_id=int(staff_user.id or 0),
                    role=cls.ROLE_INSTALLER,
                    status=StaffTenantMembershipService.membership_status(
                        staff_user.status
                    ),
                )
            return staff_user

        staff_user.display_name = installer.name
        staff_user.default_rate = installer.default_rate
        staff_user.telegram_id = installer.telegram_id
        staff_user.primary_role = cls.primary_role(staff_user)
        roles = cls.normalize_roles(staff_user.roles)
        if cls.ROLE_INSTALLER not in roles:
            roles.append(cls.ROLE_INSTALLER)
        staff_user.roles = roles
        session.add(staff_user)
        await session.flush()
        if tenant_scope is not None:
            await StaffTenantMembershipService.ensure(
                session,
                tenant_id=tenant_scope.tenant_id,
                staff_user_id=int(staff_user.id or 0),
                role=cls.primary_role(staff_user),
                status=StaffTenantMembershipService.membership_status(
                    staff_user.status
                ),
            )
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
