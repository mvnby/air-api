"""One-use Telegram proofs. The bot proves its sender; the browser authorizes writes."""

from datetime import datetime, timedelta, timezone
import secrets
from uuid import uuid4

from sqlalchemy import update
from sqlmodel import select

from models import Installer, StaffUser, Storefront, Tenant, TenantAuditEvent, TenantMembership
from models.staff_telegram import StaffTelegramChallenge
from services.credential_service import CredentialService
from services.legacy_owner_auth_guard import LegacyOwnerAuthGuard
from services.legacy_owner_managed_identity_service import LegacyOwnerManagedIdentityService
from services.account_access_service import AccountAccessResolver
from services.manager_tenant_access_service import ManagerTenantAccessResolutionError
from services.staff_tenant_membership_service import StaffTenantMembershipService
from services.staff_telegram_security import StaffTelegramError, bot_username, digest, require_browser
from services.staff_user_service import StaffUserService
from services.staff_telegram_notifications import retire_telegram_identity
from core.request_context import current_request_id


def utc_now():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class StaffTelegramService:
    TTL = timedelta(minutes=5)

    @staticmethod
    def response(row):
        status = "expired" if aware(row.expires_at) <= utc_now() and row.status not in {"confirmed", "completed", "canceled", "denied"} else row.status
        return {
            "challenge_id": row.id, "expires_at": row.expires_at, "status": status,
            "telegram": ({"id": row.telegram_id, "username": row.telegram_username,
                          "display_name": row.telegram_display_name or row.telegram_username or "Telegram"}
                         if row.telegram_id else None),
        }

    @staticmethod
    async def _get(session, challenge_id, *, lock=False):
        statement = select(StaffTelegramChallenge).where(StaffTelegramChallenge.id == challenge_id)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        row = (await session.execute(statement)).scalar_one_or_none()
        if row is None:
            raise StaffTelegramError("telegram_challenge_not_found", "Подключение не найдено", 404)
        return row

    @staticmethod
    def _live(row):
        if aware(row.expires_at) <= utc_now():
            raise StaffTelegramError("telegram_challenge_expired", "Ссылка истекла. Создайте новую")
        if row.status in {"canceled", "denied", "completed", "confirmed"}:
            raise StaffTelegramError("telegram_challenge_used", "Ссылка уже использована")

    @staticmethod
    async def _identity(session, auth):
        if auth.staff_user_id is None:
            raise StaffTelegramError("self_service_unavailable", "Сначала завершите переход владельца на личную учётную запись")
        await LegacyOwnerManagedIdentityService.ensure_self_service_allowed(session, staff_user_id=auth.staff_user_id)
        await StaffTenantMembershipService.lock_tenant(session, tenant_id=auth.tenant_id)
        user = (await session.execute(select(StaffUser).where(
            StaffUser.id == auth.staff_user_id,
        ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        membership = (await session.execute(
            select(TenantMembership)
            .join(Tenant, Tenant.id == TenantMembership.tenant_id)
            .join(Storefront, Storefront.tenant_id == Tenant.id)
            .where(
                TenantMembership.tenant_id == auth.tenant_id,
                TenantMembership.staff_user_id == auth.staff_user_id,
                TenantMembership.status == "active",
                TenantMembership.role.in_(AccountAccessResolver.ROLES),
                Tenant.status == "active", Tenant.demo_read_only.is_(False),
                Storefront.id == auth.storefront_id, Storefront.status == "active",
            ).execution_options(populate_existing=True)
        )).scalar_one_or_none()
        if (user is None or user.status != "active" or getattr(user, "merged_into_staff_user_id", None)
                or user.auth_version != auth.auth_version or membership is None):
            raise StaffTelegramError("telegram_session_changed", "Войдите заново", 401)
        return user

    @classmethod
    async def start(cls, session, *, purpose, browser_secret, auth=None):
        username = await bot_username()
        user = await cls._identity(session, auth) if purpose == "link" else None
        if user is not None:
            await session.execute(update(StaffTelegramChallenge).where(
                StaffTelegramChallenge.purpose == "link", StaffTelegramChallenge.staff_user_id == user.id,
                StaffTelegramChallenge.status.in_(["pending", "claimed"]),
            ).values(status="canceled"))
        elif browser_secret:
            await session.execute(update(StaffTelegramChallenge).where(
                StaffTelegramChallenge.purpose == "login", StaffTelegramChallenge.browser_hash == digest(browser_secret),
                StaffTelegramChallenge.status.in_(["pending", "approval_pending", "approved"]),
            ).values(status="canceled"))
        secret = secrets.token_urlsafe(32)
        token = secrets.token_urlsafe(32)
        row = StaffTelegramChallenge(
            id=uuid4().hex, purpose=purpose, token_hash=digest(token), browser_hash=digest(secret),
            staff_user_id=user.id if user else None, auth_version=user.auth_version if user else None,
            previous_telegram_id=user.telegram_id if user else None,
            expires_at=utc_now() + cls.TTL,
            browser_code=f"{secrets.randbelow(100_000_000):08d}" if purpose == "login" else None,
        )
        session.add(row)
        await session.commit()
        return {**cls.response(row), "deep_link": f"https://t.me/{username}?start={purpose}_{token}",
                "browser_code": row.browser_code}, secret

    @classmethod
    async def status(cls, session, *, challenge_id, browser_secret, purpose, auth=None):
        row = await cls._get(session, challenge_id)
        require_browser(row, browser_secret)
        if row.purpose != purpose:
            raise StaffTelegramError("telegram_challenge_not_found", "Подключение не найдено", 404)
        expected_version = row.auth_version + (1 if row.status == "confirmed" else 0) if row.auth_version is not None else None
        if purpose == "link" and (auth.staff_user_id != row.staff_user_id or auth.auth_version != expected_version):
            raise StaffTelegramError("telegram_session_changed", "Войдите заново", 401)
        return cls.response(row)

    @classmethod
    async def claim(cls, session, *, token, telegram_id, telegram_username, telegram_display_name, chat_id, message_id, purpose):
        if telegram_id != chat_id or telegram_id <= 0:
            raise StaffTelegramError("telegram_private_chat_required", "Откройте личный чат с ботом", 403)
        row = (await session.execute(select(StaffTelegramChallenge).where(
            StaffTelegramChallenge.token_hash == digest(token),
        ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if row is None or row.purpose != purpose:
            raise StaffTelegramError("telegram_challenge_not_found", "Ссылка недействительна", 404)
        cls._live(row)
        if row.telegram_id is not None:
            if row.telegram_id != telegram_id:
                raise StaffTelegramError("telegram_challenge_claimed", "Ссылка уже открыта другим аккаунтом")
            # Re-delivery of the same /start is harmless and returns its receipt.
            await session.commit()
            return {**cls.response(row), "purpose": row.purpose, "browser_code": row.browser_code}
        if purpose == "login":
            user = await cls._login_user(session, telegram_id)
            row.staff_user_id, row.auth_version = user.id, user.auth_version
            row.status = "approval_pending"
        else:
            row.status = "claimed"
        row.telegram_id = telegram_id
        row.telegram_username = telegram_username
        row.telegram_display_name = telegram_display_name
        row.claim_key = f"{chat_id}:{message_id}"
        await session.commit()
        return {**cls.response(row), "purpose": row.purpose, "browser_code": row.browser_code}

    @staticmethod
    async def _login_user(session, telegram_id):
        user = (await session.execute(select(StaffUser).where(StaffUser.telegram_id == telegram_id))).scalar_one_or_none()
        if (user is None or user.status != "active" or getattr(user, "merged_into_staff_user_id", None)):
            raise StaffTelegramError("telegram_login_unavailable", "Для этого Telegram вход недоступен", 403)
        state = await LegacyOwnerAuthGuard.state(session)
        if not LegacyOwnerAuthGuard.allows_staff_identity(state, staff_user_id=user.id, username=user.username or ""):
            raise StaffTelegramError("telegram_login_unavailable", "Для этого Telegram вход недоступен", 403)
        if LegacyOwnerManagedIdentityService.is_bound(state, staff_user_id=user.id):
            if not await LegacyOwnerManagedIdentityService.exact_bound_staff_identity_allowed(session, state=state, user=user):
                raise StaffTelegramError("telegram_login_unavailable", "Для этого Telegram вход недоступен", 403)
        try:
            await AccountAccessResolver.personal(session, staff_user_id=user.id)
        except ManagerTenantAccessResolutionError:
            raise StaffTelegramError("telegram_login_unavailable", "Для этого Telegram вход недоступен", 403) from None
        return user

    @classmethod
    async def decide(cls, session, *, challenge_id, telegram_id, approve):
        row = await cls._get(session, challenge_id, lock=True)
        cls._live(row)
        if row.purpose != "login" or row.telegram_id != telegram_id or row.status not in {"approval_pending", "approved"}:
            raise StaffTelegramError("telegram_login_unavailable", "Запрос входа недоступен", 403)
        if approve:
            user = await cls._login_user(session, telegram_id)
            if user.id != row.staff_user_id or user.auth_version != row.auth_version:
                raise StaffTelegramError("telegram_session_changed", "Создайте новый запрос входа", 401)
        row.status = "approved" if approve else "denied"
        await session.commit()
        return {"challenge_id": row.id, "status": row.status}

    @staticmethod
    def _audit(session, user, auth, action, before):
        session.add(TenantAuditEvent(
            tenant_id=auth.tenant_id, storefront_id=auth.storefront_id,
            actor_staff_user_id=user.id, actor_username=auth.username,
            action=action, entity_type="staff_user", entity_id=user.id,
            request_id=current_request_id(),
            change_set={"telegram_id": {"before": before, "after": user.telegram_id}, "auth_version": user.auth_version},
        ))

    @classmethod
    async def confirm(cls, session, *, challenge_id, browser_secret, auth, telegram_id):
        user = await cls._identity(session, auth)
        row = await cls._get(session, challenge_id, lock=True)
        require_browser(row, browser_secret)
        cls._live(row)
        if (row.purpose != "link" or row.staff_user_id != user.id or row.auth_version != user.auth_version
                or row.previous_telegram_id != user.telegram_id or row.status != "claimed" or row.telegram_id != telegram_id):
            raise StaffTelegramError("telegram_challenge_conflict", "Данные подключения изменились. Создайте новую ссылку")
        collision = await session.scalar(select(StaffUser.id).where(StaffUser.telegram_id == telegram_id, StaffUser.id != user.id))
        if collision is not None:
            raise StaffTelegramError("telegram_already_linked", "Этот Telegram уже связан с другой учётной записью")
        before = user.telegram_id
        if before != telegram_id:
            await retire_telegram_identity(session, before, user.id)
        user.telegram_id, user.telegram_username = telegram_id, row.telegram_username
        user.telegram_verified_at = utc_now()
        user.auth_version += 1
        if user.legacy_installer_id:
            installer = await session.get(Installer, user.legacy_installer_id)
            if installer:
                installer.telegram_id = telegram_id
        row.status, row.consumed_at = "confirmed", utc_now()
        await session.execute(update(StaffTelegramChallenge).where(
            StaffTelegramChallenge.staff_user_id == user.id, StaffTelegramChallenge.id != row.id,
            StaffTelegramChallenge.status.in_(["pending", "claimed", "approval_pending", "approved"]),
        ).values(status="canceled"))
        cls._audit(session, user, auth, "staff.telegram_linked", before)
        await session.commit()
        return user

    @classmethod
    async def disconnect(cls, session, *, auth, current_password):
        user = await cls._identity(session, auth)
        if not user.username or not user.password_hash:
            raise StaffTelegramError("telegram_last_login_factor", "Сначала настройте логин и пароль")
        if not await CredentialService.verify_password_async(current_password, user.password_hash):
            raise StaffTelegramError("invalid_current_password", "Текущий пароль указан неверно", 400)
        before = user.telegram_id
        await retire_telegram_identity(session, before, user.id)
        user.telegram_id = user.telegram_username = user.telegram_verified_at = None
        user.auth_version += 1
        if user.legacy_installer_id:
            installer = await session.get(Installer, user.legacy_installer_id)
            if installer:
                installer.telegram_id = None
        await session.execute(update(StaffTelegramChallenge).where(
            StaffTelegramChallenge.staff_user_id == user.id,
            StaffTelegramChallenge.status.in_(["pending", "claimed", "approval_pending", "approved"]),
        ).values(status="canceled"))
        cls._audit(session, user, auth, "staff.telegram_disconnected", before)
        await session.commit()
        return user

    @classmethod
    async def complete_login(cls, session, *, challenge_id, browser_secret):
        snapshot = await cls._get(session, challenge_id)
        require_browser(snapshot, browser_secret)
        if snapshot.purpose != "login" or not snapshot.staff_user_id:
            raise StaffTelegramError("telegram_login_unavailable", "Сначала подтвердите вход в боте", 403)
        # Snapshot first without a lock; the final locked read below is authoritative.
        await LegacyOwnerAuthGuard.state(session, for_update=True)
        access = await AccountAccessResolver.personal(session, staff_user_id=snapshot.staff_user_id)
        await StaffTenantMembershipService.lock_tenant(session, tenant_id=access.tenant_scope.tenant_id)
        user = (await session.execute(select(StaffUser).where(
            StaffUser.id == snapshot.staff_user_id,
        ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        row = await cls._get(session, challenge_id, lock=True)
        require_browser(row, browser_secret)
        cls._live(row)
        if row.status != "approved" or user is None or user.auth_version != row.auth_version:
            raise StaffTelegramError("telegram_login_unavailable", "Создайте новый запрос входа", 403)
        current = await cls._login_user(session, row.telegram_id)
        if current.id != row.staff_user_id:
            raise StaffTelegramError("telegram_login_unavailable", "Создайте новый запрос входа", 403)
        row.status, row.consumed_at = "completed", utc_now()
        user.last_login_at = utc_now().replace(tzinfo=None)
        user.telegram_verified_at = utc_now()
        await session.commit()
        return user
