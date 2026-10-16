"""Whitelisted self profile writes; never changes credentials or company rights."""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from api_contracts.manager_profile import ManagerOwnProfileResponse, ManagerOwnProfileUpdate
from core.request_context import current_request_id
from core.security import AuthenticatedUser
from models import Installer, StaffAvatar, StaffUser, Tenant, TenantAuditEvent, TenantMembership
from services.legacy_owner_managed_identity_service import LegacyOwnerManagedIdentityService
from services.staff_avatar_service import staff_avatar_url
from services.staff_tenant_membership_service import StaffTenantMembershipService
from services.staff_user_service import StaffUserService


class ManagerProfileError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 409):
        super().__init__(message)
        self.code, self.status_code = code, status_code


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class ManagerProfileService:
    @staticmethod
    def response(user: StaffUser, *, auth: AuthenticatedUser) -> ManagerOwnProfileResponse:
        return ManagerOwnProfileResponse(
            staff_user_id=user.id, display_name=user.display_name, username=user.username,
            phone=user.phone, email=user.email, avatar_url=staff_avatar_url(user, tenant_id=auth.tenant_id),
            updated_at=utc(user.updated_at or user.created_at),
            can_change_password=auth.can_change_password, must_change_password=auth.must_change_password,
            personal_read_only=auth.demo_read_only,
            telegram_linked=user.telegram_id is not None,
            telegram_username=user.telegram_username,
            telegram_notifications_enabled=user.telegram_notifications_enabled,
        )

    @staticmethod
    async def read(session: AsyncSession, *, auth: AuthenticatedUser) -> StaffUser:
        user = await session.get(StaffUser, auth.staff_user_id) if auth.staff_user_id else None
        if user is None or not StaffUserService.is_active(user):
            raise ManagerProfileError("profile_unavailable", "Личный профиль недоступен", 409)
        return user

    @classmethod
    async def lock_self(
        cls, session: AsyncSession, *, auth: AuthenticatedUser, expected_updated_at: datetime,
    ) -> StaffUser:
        if auth.staff_user_id is None:
            raise ManagerProfileError("profile_unavailable", "Личный профиль недоступен")
        # All identity writes use the same state -> tenant -> staff lock order.
        await LegacyOwnerManagedIdentityService.ensure_self_service_allowed(
            session, staff_user_id=auth.staff_user_id,
        )
        await StaffTenantMembershipService.lock_tenant(session, tenant_id=auth.tenant_scope().tenant_id)
        user = await session.scalar(
            select(StaffUser).where(StaffUser.id == auth.staff_user_id)
            .with_for_update().execution_options(populate_existing=True)
        )
        membership = await session.scalar(select(TenantMembership).where(
            TenantMembership.staff_user_id == auth.staff_user_id,
            TenantMembership.tenant_id == auth.tenant_id,
            TenantMembership.status == "active",
        ).execution_options(populate_existing=True))
        tenant = await session.get(Tenant, auth.tenant_id, populate_existing=True)
        if (user is None or not StaffUserService.is_active(user) or membership is None
                or tenant is None or tenant.status != "active"
                or (auth.auth_version is not None and user.auth_version != auth.auth_version)):
            raise ManagerProfileError("invalid_session", "Войдите в систему повторно", 401)
        if utc(user.updated_at or user.created_at) != utc(expected_updated_at):
            raise ManagerProfileError("profile_changed", "Профиль уже изменён. Обновите данные и повторите действие")
        return user

    @classmethod
    async def update(
        cls, session: AsyncSession, *, auth: AuthenticatedUser, payload: ManagerOwnProfileUpdate,
    ) -> ManagerOwnProfileResponse:
        user = await cls.lock_self(session, auth=auth, expected_updated_at=payload.expected_updated_at)
        changes = {}
        for field in payload.model_fields_set - {"expected_updated_at"}:
            before, after = getattr(user, field), getattr(payload, field)
            if before != after:
                changes[field] = {"before": before, "after": after}
                setattr(user, field, after)
        if changes:
            if "display_name" in changes and user.legacy_installer_id is not None:
                installer = await session.scalar(select(Installer).where(
                    Installer.id == user.legacy_installer_id,
                ).with_for_update().execution_options(populate_existing=True))
                if installer is not None:
                    installer.name = user.display_name
                    session.add(installer)
            cls.audit(session, auth=auth, user=user, action="staff_profile.updated", changes=changes)
            # StaffUser predates timezone-aware columns; persist UTC-naive here
            # and expose an explicit UTC timestamp in the profile contract.
            user.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            session.add(user)
        await session.commit()
        await session.refresh(user)
        return cls.response(user, auth=auth)

    @classmethod
    async def set_avatar(
        cls, session: AsyncSession, *, auth: AuthenticatedUser, expected_updated_at: datetime,
        photo: tuple[bytes, str] | None,
    ) -> ManagerOwnProfileResponse:
        user = await cls.lock_self(session, auth=auth, expected_updated_at=expected_updated_at)
        avatar = await session.scalar(select(StaffAvatar).where(
            StaffAvatar.staff_user_id == user.id,
        ).with_for_update().execution_options(populate_existing=True))
        before, after = user.avatar_version, photo[1] if photo else None
        if before != after:
            now = datetime.now(timezone.utc)
            if photo is None:
                if avatar is not None:
                    await session.delete(avatar)
            elif avatar is None:
                session.add(StaffAvatar(staff_user_id=user.id, content=photo[0], content_hash=after, updated_at=now))
            else:
                avatar.content, avatar.content_hash, avatar.updated_at = photo[0], after, now
                session.add(avatar)
            user.avatar_version, user.updated_at = after, now.replace(tzinfo=None)
            session.add(user)
            cls.audit(session, auth=auth, user=user, action="staff_avatar.updated", changes={
                "avatar_version": {"before": before, "after": after},
            })
        await session.commit()
        await session.refresh(user)
        return cls.response(user, auth=auth)

    @staticmethod
    def audit(session, *, auth, user, action, changes):
        session.add(TenantAuditEvent(
            tenant_id=auth.tenant_id, storefront_id=auth.storefront_id,
            actor_staff_user_id=user.id, actor_username=auth.username,
            action=action, entity_type="staff_user", entity_id=user.id,
            request_id=current_request_id(), change_set=changes,
        ))
