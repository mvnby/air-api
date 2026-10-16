"""Reviewed company invitations bind a proven person, never an email address."""
import asyncio
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import get_args

from sqlmodel import select
from api_contracts.manager_invitations import InvitationRole
from crud.staff_invitation import StaffInvitationDAO
from crud.tenancy import TenancyDAO
from core.request_context import current_request_id
from models import StaffUser, Tenant, TenantMembership, TenantAuditEvent
from models.staff_invitation import StaffInvitation
from services.credential_service import CredentialService
from services.legacy_owner_auth_guard import LegacyOwnerAuthGuard
from services.legacy_owner_auth_state_service import LegacyOwnerAuthStateService
from services.legacy_owner_managed_identity_service import LegacyOwnerManagedIdentityService
from services.login_throttle_service import LoginThrottleService
from services.staff_access_policy import StaffAccessPolicy
from services.staff_user_service import StaffUserService


def now():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


class StaffInvitationError(ValueError):
    def __init__(self, code, message, status_code=409):
        super().__init__(message)
        self.code, self.status_code = code, status_code


class InvitationCredentialThrottle(LoginThrottleService):
    _FINGERPRINT_DOMAIN = b"staff-invitation-password\0"
    _SOURCE_FINGERPRINT_DOMAIN = b"staff-invitation-password-source\0"
    _GLOBAL_FINGERPRINT_DOMAIN = b"staff-invitation-password-global\0"


@dataclass(frozen=True)
class InvitationIdentitySnapshot:
    id: int
    username: str | None
    telegram_id: int | None
    auth_version: int


@dataclass(frozen=True)
class CredentialProof:
    staff_user_id: int
    auth_version: int
    password_hash: str | None = None


class StaffInvitationService:
    ALLOWED_ROLES = frozenset(get_args(InvitationRole))

    @staticmethod
    def status(row):
        if row.accepted_at:
            return "accepted"
        if row.revoked_at:
            return "revoked"
        return "expired" if aware(row.expires_at) <= now() else "pending"

    @classmethod
    def require_pending(cls, row):
        if row is None or cls.status(row) != "pending":
            raise StaffInvitationError("invitation_unavailable", "Приглашение недоступно или срок действия истёк", 404)

    @staticmethod
    async def _lock(session, *, tenant_id, staff_ids):
        state = await LegacyOwnerAuthStateService.get(session, for_update=True)
        tenant = await session.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update().execution_options(populate_existing=True))
        if tenant is None or tenant.status != "active" or tenant.demo_read_only:
            raise StaffInvitationError("company_access_denied", "Приглашения в эту компанию недоступны", 403)
        users = (await session.execute(select(StaffUser).where(StaffUser.id.in_(staff_ids))
                                       .order_by(StaffUser.id).with_for_update().execution_options(populate_existing=True))).scalars().all()
        memberships = (await session.execute(select(TenantMembership).where(TenantMembership.staff_user_id.in_(staff_ids))
                                             .order_by(TenantMembership.id).with_for_update().execution_options(populate_existing=True))).scalars().all()
        return state, tenant, {user.id: user for user in users}, list(memberships)

    @staticmethod
    async def _inviter(session, *, state, tenant, user, memberships, role, expected_version=None):
        if role not in StaffInvitationService.ALLOWED_ROLES:
            raise StaffInvitationError("invitation_role_invalid", "Выберите доступную роль сотрудника", 400)
        if (user is None or not StaffUserService.is_active(user) or user.must_change_password
                or (expected_version is not None and user.auth_version != expected_version)
                or not LegacyOwnerAuthGuard.allows_staff_identity(state, staff_user_id=user.id, username=user.username or "")):
            raise StaffInvitationError("inviter_access_changed", "Права приглашающего изменились", 403)
        platform = LegacyOwnerAuthGuard.allows_bound_staff(state, staff_user_id=user.id)
        if platform and not await LegacyOwnerManagedIdentityService.exact_bound_staff_identity_allowed(session, state=state, user=user):
            raise StaffInvitationError("inviter_access_changed", "Права приглашающего изменились", 403)
        membership = next((row for row in memberships if row.staff_user_id == user.id and row.tenant_id == tenant.id and row.status == "active"), None)
        StaffAccessPolicy.validate_mutation(
            actor_role=membership.role if membership else "", is_platform_owner=platform,
            target_role=None, requested_role=role,
        )

    @staticmethod
    async def _default_site(session, tenant_id):
        rows = await TenancyDAO.active_company_defaults(session, tenant_id=tenant_id)
        if len(rows) != 1:
            raise StaffInvitationError("company_access_denied", "Рабочее пространство компании недоступно", 403)
        return rows[0][1]

    @staticmethod
    def _audit(session, *, tenant_id, site_id, actor, invitation, action, changes):
        session.add(TenantAuditEvent(
            tenant_id=tenant_id, storefront_id=site_id, actor_staff_user_id=actor.id,
            actor_username=actor.username or str(actor.telegram_id or actor.id), action=action,
            entity_type="staff_invitation", entity_id=invitation.id, request_id=current_request_id(), change_set=changes,
        ))

    @classmethod
    async def create(cls, session, *, auth, role):
        if auth.staff_user_id is None:
            raise StaffInvitationError("staff_identity_required", "Войдите через личную учётную запись", 403)
        state, tenant, users, memberships = await cls._lock(session, tenant_id=auth.tenant_id, staff_ids=[auth.staff_user_id])
        actor = users.get(auth.staff_user_id)
        await cls._inviter(session, state=state, tenant=tenant, user=actor, memberships=memberships, role=role, expected_version=auth.auth_version)
        site = await cls._default_site(session, tenant.id)
        token = secrets.token_urlsafe(32)
        invitation = StaffInvitation(tenant_id=tenant.id, created_by_staff_user_id=actor.id,
                                     token_hash=digest(token), role=role, expires_at=now() + timedelta(days=7))
        session.add(invitation)
        await session.flush()
        cls._audit(session, tenant_id=tenant.id, site_id=site.id, actor=actor, invitation=invitation,
                   action="staff_invitation.created", changes={"role": role, "expires_at": invitation.expires_at.isoformat()})
        result = {"id": invitation.id, "role": role, "expires_at": invitation.expires_at,
                  "invite_url": "/manager/invite#token=" + token}
        await session.commit()
        return result

    @classmethod
    async def list(cls, session, *, auth, page, limit):
        rows, total = await StaffInvitationDAO.list(session, tenant_id=auth.tenant_id, page=page, limit=limit)
        return {"items": [{"id": row.id, "role": row.role, "created_at": row.created_at,
                           "expires_at": row.expires_at, "status": cls.status(row)} for row in rows],
                "total": total, "page": page, "limit": limit}

    @classmethod
    async def revoke(cls, session, *, auth, invitation_id):
        if auth.staff_user_id is None:
            raise StaffInvitationError("staff_identity_required", "Войдите через личную учётную запись", 403)
        state, tenant, users, memberships = await cls._lock(session, tenant_id=auth.tenant_id, staff_ids=[auth.staff_user_id])
        row = await session.scalar(select(StaffInvitation).where(StaffInvitation.id == invitation_id,
                                   StaffInvitation.tenant_id == tenant.id).with_for_update().execution_options(populate_existing=True))
        if row is None:
            raise StaffInvitationError("invitation_unavailable", "Приглашение не найдено", 404)
        actor = users.get(auth.staff_user_id)
        await cls._inviter(session, state=state, tenant=tenant, user=actor, memberships=memberships, role=row.role, expected_version=auth.auth_version)
        if cls.status(row) == "pending":
            row.revoked_at = now()
            site = await cls._default_site(session, tenant.id)
            cls._audit(session, tenant_id=tenant.id, site_id=site.id, actor=actor, invitation=row,
                       action="staff_invitation.revoked", changes={"status": "revoked"})
        await session.commit()

    @classmethod
    async def preview(cls, session, *, token):
        row = await StaffInvitationDAO.by_hash(session, digest(token))
        cls.require_pending(row)
        tenant = await session.get(Tenant, row.tenant_id, populate_existing=True)
        if tenant is None or tenant.status != "active" or tenant.demo_read_only:
            raise StaffInvitationError("invitation_unavailable", "Приглашение недоступно", 404)
        return {"company_name": tenant.display_name, "role": row.role, "expires_at": row.expires_at}

    @staticmethod
    async def credentials(session, *, username, password, source):
        normalized = StaffUserService.normalize_username(username)
        reservation = await InvitationCredentialThrottle.reserve_attempt(session, normalized, source)
        user = await session.scalar(select(StaffUser).where(StaffUser.username == normalized).execution_options(populate_existing=True))
        usable = user is not None and user.status in {"active", "inactive"} and user.merged_into_staff_user_id is None and bool(user.password_hash)
        password_hash = user.password_hash if usable else CredentialService.DUMMY_PASSWORD_HASH
        proof = CredentialProof(user.id, user.auth_version, password_hash) if usable else None
        verified = await CredentialService.verify_password_async(password, password_hash)
        if not usable or not verified:
            await InvitationCredentialThrottle.record_failure(session, normalized, source, reservation=reservation)
            raise StaffInvitationError("invalid_credentials", "Неверный логин или пароль", 401)
        # Release the isolated throttle locks before taking identity/company locks.
        await InvitationCredentialThrottle.clear(session, normalized)
        return proof

    @classmethod
    async def accept(cls, session, *, payload, identity=None, source=None):
        invitation = await StaffInvitationDAO.by_hash(session, digest(payload.token))
        cls.require_pending(invitation)
        tenant_id, inviter_id = invitation.tenant_id, invitation.created_by_staff_user_id
        proof, new_hash = None, None
        if payload.mode == "existing":
            if identity is None or identity.staff_user_id is None or identity.must_change_password:
                raise StaffInvitationError("staff_identity_required", "Войдите через личную учётную запись", 401)
            proof = CredentialProof(identity.staff_user_id, identity.auth_version)
        elif payload.mode == "existing_credentials":
            proof = await cls.credentials(session, username=payload.username, password=payload.password, source=source)
        else:
            username = StaffUserService.normalize_username(payload.username)
            if not username or not payload.display_name.strip() or LegacyOwnerAuthGuard.configured_username_matches(username):
                raise StaffInvitationError("account_unavailable", "Выберите другой логин")
            new_hash = await asyncio.to_thread(CredentialService.hash_password, payload.password)
        state, tenant, users, memberships = await cls._lock(
            session, tenant_id=tenant_id, staff_ids=sorted({inviter_id} | ({proof.staff_user_id} if proof else set())),
        )
        row = await StaffInvitationDAO.by_hash(session, digest(payload.token), lock=True)
        cls.require_pending(row)
        if row.tenant_id != tenant_id or row.created_by_staff_user_id != inviter_id:
            raise StaffInvitationError("invitation_unavailable", "Приглашение изменилось")
        await cls._inviter(session, state=state, tenant=tenant, user=users.get(inviter_id), memberships=memberships, role=row.role)
        site = await cls._default_site(session, tenant.id)
        if proof:
            user = users.get(proof.staff_user_id)
            if (user is None or user.merged_into_staff_user_id is not None or user.status not in {"active", "inactive"}
                    or user.must_change_password or user.auth_version != proof.auth_version
                    or (proof.password_hash is not None and user.password_hash != proof.password_hash)
                    or not LegacyOwnerAuthGuard.allows_staff_identity(state, staff_user_id=user.id, username=user.username or "")):
                raise StaffInvitationError("identity_changed", "Войдите заново", 401)
            existing = [item for item in memberships if item.staff_user_id == user.id]
            if any(item.tenant_id == tenant.id for item in existing):
                raise StaffInvitationError("membership_exists", "Доступ к этой компании уже создан")
            if LegacyOwnerManagedIdentityService.is_bound(state, staff_user_id=user.id):
                raise StaffInvitationError("platform_owner_membership_fixed", "Владелец платформы использует доступ поддержки")
            if existing and (user.legacy_installer_id is not None or user.default_rate is not None):
                raise StaffInvitationError("installer_company_fixed", "Для исполнителя пока доступна одна компания")
            reactivated = user.status == "inactive"
            if reactivated:
                if payload.mode != "existing_credentials" or any(item.status != "disabled" for item in existing):
                    raise StaffInvitationError("identity_unavailable", "Для этой учётной записи приглашение недоступно", 403)
                user.status = "active"
                user.auth_version += 1
        else:
            if await session.scalar(select(StaffUser.id).where(StaffUser.username == username)) is not None:
                raise StaffInvitationError("account_exists", "Этот логин уже занят. Войдите в существующую учётную запись")
            user = StaffUser(username=username, display_name=payload.display_name.strip(), password_hash=new_hash,
                             password_changed_at=now(), roles=[row.role], primary_role=row.role, status="active")
            session.add(user)
            await session.flush()
            reactivated = False
        membership = TenantMembership(tenant_id=tenant.id, staff_user_id=user.id, role=row.role, status="active", permissions=[])
        session.add(membership)
        row.accepted_at, row.accepted_by_staff_user_id = now(), user.id
        cls._audit(session, tenant_id=tenant.id, site_id=site.id, actor=user, invitation=row,
                   action="staff_invitation.accepted", changes={"staff_user_id": user.id, "role": row.role,
                       "reactivated": reactivated, "auth_version": user.auth_version, "permissions": []})
        snapshot = InvitationIdentitySnapshot(user.id, user.username, user.telegram_id, user.auth_version)
        await session.commit()
        return {"tenant_id": tenant.id, "default_storefront_slug": site.slug}, snapshot
