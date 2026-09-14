"""Reviewed, fail-closed provisioning for one tenant-scoped staff identity."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.input_validation import normalize_phone_digits
from models import StaffUser, Storefront, Tenant, TenantAuditEvent, TenantMembership
from services.staff_user_service import StaffUserService
from services.credential_service import CredentialService
from services.storefront_onboarding_plan_token import StorefrontOnboardingPlanToken


class TenantManagerProvisioningBlockedError(RuntimeError):
    """The requested manager identity cannot be safely provisioned."""


_PHONE_PATTERN = re.compile(r"^\+[1-9][0-9]{7,14}$")


@dataclass(frozen=True)
class TenantManagerProvisioningRequest:
    tenant_slug: str
    storefront_slug: str
    display_name: str
    username: str
    phone: str | None
    role: str = StaffUserService.ROLE_MANAGER
    reset_password: bool = False

    @classmethod
    def normalize(
        cls,
        *,
        tenant_slug: str,
        storefront_slug: str,
        display_name: str,
        username: str,
        phone: str | None = None,
        role: str = StaffUserService.ROLE_MANAGER,
        reset_password: bool = False,
    ) -> "TenantManagerProvisioningRequest":
        normalized_tenant = str(tenant_slug or "").strip().lower()
        normalized_storefront = str(storefront_slug or "").strip().lower()
        normalized_name = str(display_name or "").strip()
        normalized_username = StaffUserService.normalize_username(username)
        normalized_phone = str(phone or "").strip() or None
        normalized_role = StaffUserService.normalize_role(role)
        if not normalized_tenant or not normalized_storefront:
            raise ValueError("Tenant and storefront slugs are required")
        if not normalized_name:
            raise ValueError("Display name is required")
        if not normalized_username:
            raise ValueError("Username is required")
        if normalized_phone is not None and not _PHONE_PATTERN.fullmatch(normalized_phone):
            raise ValueError("Phone must be a complete E.164 number")
        if normalized_role not in {
            StaffUserService.ROLE_MANAGER,
            StaffUserService.ROLE_OWNER,
        }:
            raise ValueError("Role must be manager or owner")
        if type(reset_password) is not bool:
            raise ValueError("Reset password must be an explicit boolean")
        return cls(
            tenant_slug=normalized_tenant,
            storefront_slug=normalized_storefront,
            display_name=normalized_name,
            username=normalized_username,
            phone=normalized_phone,
            role=normalized_role,
            reset_password=reset_password,
        )

    def public_dict(self) -> dict[str, Any]:
        return {
            "tenant_slug": self.tenant_slug,
            "storefront_slug": self.storefront_slug,
            "display_name": self.display_name,
            "username": self.username,
            "phone": self.phone,
            "role": self.role,
            "reset_password": self.reset_password,
        }

    @property
    def phone_digits(self) -> str:
        return normalize_phone_digits(self.phone or "")


@dataclass
class _State:
    tenant: Tenant | None
    storefront: Storefront | None
    candidates: list[StaffUser]
    memberships: list[TenantMembership]


class TenantManagerProvisioningService:
    """Plan and atomically apply a least-privilege tenant staff identity.

    The service deliberately does not commit.  The caller owns the enclosing
    transaction, so a failed post-check cannot leave a partial StaffUser or
    membership behind.
    """

    LOCK_NAMESPACE = "mvn:tenant-manager-provisioning:v1"
    AUDIT_ACTOR_USERNAME = "system:tenant-manager-provisioning"
    AUDIT_ACTION = "tenant_manager.provisioned"

    @classmethod
    async def plan(
        cls,
        session: AsyncSession,
        *,
        request: TenantManagerProvisioningRequest,
    ) -> dict[str, Any]:
        state = await cls._load(session, request=request, for_update=False)
        plan = cls._build_plan(request=request, state=state)
        return {
            **plan,
            "plan_token": StorefrontOnboardingPlanToken.issue(
                plan_digest=plan["plan_digest"]
            ),
            "plan_token_max_age_seconds": StorefrontOnboardingPlanToken.MAX_AGE_SECONDS,
        }

    @classmethod
    async def execute(
        cls,
        session: AsyncSession,
        *,
        request: TenantManagerProvisioningRequest,
        password: str | None,
        plan_token: str,
    ) -> dict[str, Any]:
        verified = StorefrontOnboardingPlanToken.verify(plan_token)
        if not await cls._try_acquire_locks(session, request=request):
            raise TenantManagerProvisioningBlockedError(
                "Another manager provisioning transaction owns this identity"
            )
        state = await cls._load(session, request=request, for_update=True)
        reviewed = cls._build_plan(request=request, state=state)
        if not hmac.compare_digest(verified.plan_digest, reviewed["plan_digest"]):
            raise TenantManagerProvisioningBlockedError(
                "Provisioning plan token is stale; run a fresh plan"
            )
        if reviewed["blockers"]:
            raise TenantManagerProvisioningBlockedError(
                "Manager provisioning preflight is blocked: "
                + "; ".join(reviewed["blockers"])
            )
        password_changes = {
            "create_staff_user",
            "reset_staff_password",
        }.intersection(reviewed["changes"])
        if password_changes and password is None:
            raise TenantManagerProvisioningBlockedError(
                "A password source is required for the reviewed credential change"
            )
        if password_changes:
            assert password is not None
            cls._validate_password(password)

        changed = False
        if not state.candidates:
            staff_user = StaffUser(
                display_name=request.display_name,
                status=StaffUserService.STATUS_ACTIVE,
                primary_role=request.role,
                roles=[request.role],
                username=request.username,
                password_hash=CredentialService.hash_password(str(password)),
                password_changed_at=datetime.now(timezone.utc),
                phone=request.phone,
            )
            session.add(staff_user)
            await session.flush()
            membership = TenantMembership(
                tenant_id=int(state.tenant.id),
                staff_user_id=int(staff_user.id),
                role=request.role,
                status="active",
            )
            session.add(membership)
            await session.flush()
            cls._add_audit_event(
                session,
                request=request,
                tenant=state.tenant,
                storefront=state.storefront,
                staff_user=staff_user,
                membership=membership,
                plan_token=plan_token,
                before_role=None,
                before_auth_version=None,
            )
            changed = True
        else:
            staff_user = state.candidates[0]
            membership = state.memberships[0]
            before_role = StaffUserService.primary_role(staff_user)
            before_auth_version = int(staff_user.auth_version)
            changed_at = datetime.now(timezone.utc)
            if "promote_staff_user_to_owner" in reviewed["changes"]:
                staff_user.primary_role = StaffUserService.ROLE_OWNER
                staff_user.roles = [StaffUserService.ROLE_OWNER]
                membership.role = StaffUserService.ROLE_OWNER
                membership.updated_at = changed_at
                session.add(staff_user)
                session.add(membership)
                changed = True
            if "reset_staff_password" in reviewed["changes"]:
                assert password is not None
                staff_user.password_hash = CredentialService.hash_password(password)
                staff_user.password_changed_at = changed_at
                staff_user.auth_version = before_auth_version + 1
                staff_user.must_change_password = False
                session.add(staff_user)
                changed = True
            if changed:
                await session.flush()
                cls._add_audit_event(
                    session,
                    request=request,
                    tenant=state.tenant,
                    storefront=state.storefront,
                    staff_user=staff_user,
                    membership=membership,
                    plan_token=plan_token,
                    before_role=before_role,
                    before_auth_version=before_auth_version,
                )
        await session.flush()

        after = await cls._load(session, request=request, for_update=False)
        postcheck_request = TenantManagerProvisioningRequest(
            tenant_slug=request.tenant_slug,
            storefront_slug=request.storefront_slug,
            display_name=request.display_name,
            username=request.username,
            phone=request.phone,
            role=request.role,
            reset_password=False,
        )
        after_plan = cls._build_plan(request=postcheck_request, state=after)
        if after_plan["blockers"] or after_plan["changes"]:
            raise TenantManagerProvisioningBlockedError(
                "Manager provisioning post-check did not reach the reviewed target state"
            )
        return {
            "mode": "execute",
            "ready": True,
            "changed": changed,
            "target": request.public_dict(),
            "staff_user_id": int(after.candidates[0].id),
            "membership_id": int(after.memberships[0].id),
        }

    @classmethod
    async def _try_acquire_locks(
        cls,
        session: AsyncSession,
        *,
        request: TenantManagerProvisioningRequest,
    ) -> bool:
        if session.get_bind().dialect.name != "postgresql":
            return True
        lock_keys = {
            f"{cls.LOCK_NAMESPACE}:tenant:{request.tenant_slug}",
            f"{cls.LOCK_NAMESPACE}:username:{request.username}",
        }
        if request.phone_digits:
            lock_keys.add(f"{cls.LOCK_NAMESPACE}:phone:{request.phone_digits}")
        for lock_key in sorted(lock_keys):
            acquired = await session.scalar(
                text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": lock_key},
            )
            if not acquired:
                return False
        return True

    @classmethod
    async def _load(
        cls,
        session: AsyncSession,
        *,
        request: TenantManagerProvisioningRequest,
        for_update: bool,
    ) -> _State:
        tenant_statement = select(Tenant).where(Tenant.slug == request.tenant_slug)
        if for_update:
            tenant_statement = tenant_statement.with_for_update(of=Tenant)
        tenant = (await session.execute(tenant_statement)).scalar_one_or_none()

        storefront: Storefront | None = None
        if tenant is not None and tenant.id is not None:
            storefront_statement = select(Storefront).where(
                Storefront.tenant_id == tenant.id,
                Storefront.slug == request.storefront_slug,
            )
            if for_update:
                storefront_statement = storefront_statement.with_for_update(of=Storefront)
            storefront = (await session.execute(storefront_statement)).scalar_one_or_none()

        username_matches = list(
            (
                await session.execute(
                    select(StaffUser.id).where(
                        func.lower(StaffUser.username) == request.username
                    )
                )
            ).scalars().all()
        )
        phone_matches: list[tuple[int, str | None]] = []
        if request.phone_digits:
            phone_matches = list(
                (
                    await session.execute(
                        select(StaffUser.id, StaffUser.phone).where(
                            StaffUser.phone.is_not(None)
                        )
                    )
                ).all()
            )
        candidate_ids = {
            int(staff_user_id)
            for staff_user_id in username_matches
            if staff_user_id is not None
        }
        candidate_ids.update(
            int(staff_user_id)
            for staff_user_id, phone in phone_matches
            if staff_user_id is not None
            and request.phone_digits
            and normalize_phone_digits(str(phone or "")) == request.phone_digits
        )
        candidate_statement = (
            select(StaffUser)
            .where(StaffUser.id.in_(sorted(candidate_ids)))
            .order_by(StaffUser.id.asc())
        )
        if for_update:
            candidate_statement = candidate_statement.with_for_update(of=StaffUser)
        candidates = list((await session.execute(candidate_statement)).scalars().all())

        memberships: list[TenantMembership] = []
        if len(candidates) == 1 and candidates[0].id is not None:
            membership_statement = (
                select(TenantMembership)
                .where(TenantMembership.staff_user_id == candidates[0].id)
                .order_by(TenantMembership.id.asc())
            )
            if for_update:
                membership_statement = membership_statement.with_for_update(
                    of=TenantMembership
                )
            memberships = list(
                (await session.execute(membership_statement)).scalars().all()
            )
        return _State(
            tenant=tenant,
            storefront=storefront,
            candidates=candidates,
            memberships=memberships,
        )

    @classmethod
    def _build_plan(
        cls,
        *,
        request: TenantManagerProvisioningRequest,
        state: _State,
    ) -> dict[str, Any]:
        blockers = cls._blockers(request=request, state=state)
        changes: list[str] = []
        if not blockers and not state.candidates:
            changes.extend(
                ["create_staff_user", f"create_active_{request.role}_membership"]
            )
        elif not blockers and state.candidates:
            if (
                request.role == StaffUserService.ROLE_OWNER
                and StaffUserService.primary_role(state.candidates[0])
                == StaffUserService.ROLE_MANAGER
            ):
                changes.append("promote_staff_user_to_owner")
            if request.reset_password:
                changes.append("reset_staff_password")
        current = cls._public_state(state)
        digest_payload = {
            "version": 2,
            "request": request.public_dict(),
            "current": current,
            "blockers": blockers,
            "changes": changes,
        }
        encoded = json.dumps(
            digest_payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return {
            "mode": "plan",
            "ready": not blockers,
            "target": request.public_dict(),
            "current": current,
            "blockers": blockers,
            "changes": changes,
            "plan_digest": hashlib.sha256(encoded).hexdigest(),
        }

    @classmethod
    def _blockers(
        cls,
        *,
        request: TenantManagerProvisioningRequest,
        state: _State,
    ) -> list[str]:
        blockers: list[str] = []
        tenant = state.tenant
        storefront = state.storefront
        if tenant is None:
            blockers.append("Target tenant does not exist")
        elif tenant.status != "active" or tenant.is_system:
            blockers.append("Target tenant must be active and non-system")
        if storefront is None:
            blockers.append("Target storefront does not exist inside the target tenant")
        elif storefront.status != "active" or not storefront.is_default:
            blockers.append("Target storefront must be active and default")
        if len(state.candidates) > 1:
            blockers.append("Username and phone resolve to different staff users")
        if len(state.candidates) == 1:
            user = state.candidates[0]
            if user.username != request.username:
                blockers.append("Existing staff user does not match the username")
            if request.phone_digits and (
                normalize_phone_digits(str(user.phone or "")) != request.phone_digits
            ):
                blockers.append("Existing staff user does not match the requested phone")
            if user.display_name != request.display_name:
                blockers.append("Existing staff user has a different display name")
            if user.status != StaffUserService.STATUS_ACTIVE:
                blockers.append("Existing staff user is not active")
            current_role = StaffUserService.primary_role(user)
            allowed_current_roles = {request.role}
            if request.role == StaffUserService.ROLE_OWNER:
                allowed_current_roles.add(StaffUserService.ROLE_MANAGER)
            if current_role not in allowed_current_roles:
                blockers.append("Existing staff user cannot be converted to the requested role")
            if StaffUserService.normalize_roles(user.roles) != [current_role]:
                blockers.append("Existing staff user has extraneous global roles")
            if user.legacy_installer_id is not None:
                blockers.append("Existing staff user is linked to legacy installer privileges")
            if not user.password_hash:
                blockers.append("Existing staff user has no password credential")
            if user.telegram_id is not None:
                blockers.append("Existing staff user has a Telegram identity")
            if user.telegram_username:
                blockers.append("Existing staff user has a Telegram username")
            if len(state.memberships) != 1:
                blockers.append("Existing staff user must have exactly one tenant membership")
            elif (
                tenant is None
                or state.memberships[0].tenant_id != tenant.id
                or state.memberships[0].role != current_role
                or state.memberships[0].status != "active"
            ):
                blockers.append("Existing staff user lacks the exact active tenant membership")
        return blockers

    @staticmethod
    def _public_state(state: _State) -> dict[str, Any]:
        return {
            "tenant": None
            if state.tenant is None
            else {
                "id": int(state.tenant.id),
                "status": state.tenant.status,
                "is_system": bool(state.tenant.is_system),
            },
            "storefront": None
            if state.storefront is None
            else {
                "id": int(state.storefront.id),
                "tenant_id": int(state.storefront.tenant_id),
                "status": state.storefront.status,
                "is_default": bool(state.storefront.is_default),
            },
            "staff_users": [
                {
                    "id": int(user.id),
                    "username": user.username,
                    "display_name": user.display_name,
                    "phone": user.phone,
                    "status": user.status,
                    "primary_role": StaffUserService.primary_role(user),
                    "roles": StaffUserService.normalize_roles(user.roles),
                    "legacy_installer_id": user.legacy_installer_id,
                    "telegram_id": user.telegram_id,
                    "telegram_username": user.telegram_username,
                    "auth_version": int(user.auth_version),
                    "credential_changed_at": (
                        user.password_changed_at.isoformat()
                        if user.password_changed_at is not None
                        else None
                    ),
                    "must_change_password": bool(user.must_change_password),
                }
                for user in state.candidates
            ],
            "memberships": [
                {
                    "id": int(membership.id),
                    "tenant_id": membership.tenant_id,
                    "role": membership.role,
                    "status": membership.status,
                }
                for membership in state.memberships
            ],
        }

    @staticmethod
    def _validate_password(password: str) -> None:
        CredentialService.validate_password(password)

    @staticmethod
    def _add_audit_event(
        session: AsyncSession,
        *,
        request: TenantManagerProvisioningRequest,
        tenant: Tenant | None,
        storefront: Storefront | None,
        staff_user: StaffUser,
        membership: TenantMembership,
        plan_token: str,
        before_role: str | None,
        before_auth_version: int | None,
    ) -> None:
        if (
            tenant is None
            or storefront is None
            or tenant.id is None
            or storefront.id is None
            or staff_user.id is None
            or membership.id is None
        ):
            raise TenantManagerProvisioningBlockedError(
                "Provisioning audit target is incomplete"
            )
        request_id = "tenant-manager-" + hashlib.sha256(
            plan_token.encode("utf-8")
        ).hexdigest()[:32]
        created = before_role is None
        role_changed = before_role != request.role
        auth_version_changed = (
            before_auth_version is None
            or int(staff_user.auth_version) != before_auth_version
        )
        change_set: dict[str, Any] = {}
        if created:
            change_set.update(
                {
                    "display_name": {"before": None, "after": request.display_name},
                    "username": {"before": None, "after": request.username},
                    "phone": {"before": None, "after": request.phone},
                }
            )
        if created or role_changed:
            change_set.update(
                {
                    "primary_role": {"before": before_role, "after": request.role},
                    "membership": {
                        "before": (
                            None
                            if created
                            else {
                                "id": int(membership.id),
                                "tenant_id": int(tenant.id),
                                "role": before_role,
                                "status": "active",
                            }
                        ),
                        "after": {
                            "id": int(membership.id),
                            "tenant_id": int(tenant.id),
                            "role": request.role,
                            "status": "active",
                        },
                    },
                }
            )
        if auth_version_changed:
            change_set["auth_version"] = {
                "before": before_auth_version,
                "after": int(staff_user.auth_version),
            }
        if before_auth_version is not None and auth_version_changed:
            change_set["sessions_revoked"] = True
        session.add(
            TenantAuditEvent(
                tenant_id=int(tenant.id),
                storefront_id=int(storefront.id),
                actor_staff_user_id=None,
                actor_username=TenantManagerProvisioningService.AUDIT_ACTOR_USERNAME,
                action=TenantManagerProvisioningService.AUDIT_ACTION,
                entity_type="staff_user",
                entity_id=int(staff_user.id),
                request_id=request_id,
                change_set=change_set,
            )
        )


__all__ = [
    "TenantManagerProvisioningBlockedError",
    "TenantManagerProvisioningRequest",
    "TenantManagerProvisioningService",
]
