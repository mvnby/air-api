"""Reviewed compatibility cutover for the runtime-env system owner.

The boundary never accepts or returns the runtime credential. It targets only
the canonical ``mvn/main`` system scope and leaves transaction ownership to its
caller so state, identity, membership, and audit changes remain atomic.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    LegacyOwnerAuthState,
    StaffUser,
    Storefront,
    Tenant,
    TenantAuditEvent,
    TenantMembership,
)
from services.credential_service import CredentialPolicyError, CredentialService
from services.legacy_owner_auth_state_service import LegacyOwnerAuthStateService
from services.legacy_owner_cutover_plan import (
    LegacyOwnerPlanToken,
    VerifiedLegacyOwnerPlanToken,
)
from services.legacy_owner_cutover_types import (
    LegacyOwnerCutoverState as _CutoverState,
    LegacyOwnerPlanAction as PlanAction,
    LegacyOwnerRuntimeIdentity as _RuntimeIdentity,
)
from services.legacy_owner_runtime_credential import LegacyOwnerRuntimeCredential
from services.staff_user_service import StaffUserService


class LegacyOwnerCutoverBlockedError(RuntimeError):
    """The compatibility cutover cannot safely proceed."""


class LegacyOwnerCutoverService:
    SYSTEM_TENANT_SLUG = "mvn"
    SYSTEM_STOREFRONT_SLUG = "main"
    CREATED_DISPLAY_NAME = "System Owner"
    LOCK_KEY = "mvn:legacy-owner-cutover:v1"
    AUDIT_ACTOR = "system:legacy-owner-cutover"
    CUTOVER_AUDIT_ACTION = "legacy_owner.cutover_completed"
    ROLLBACK_AUDIT_ACTION = "legacy_owner.rollback_completed"

    @classmethod
    async def plan(
        cls,
        session: AsyncSession,
        *,
        for_action: PlanAction = "cutover",
    ) -> dict[str, Any]:
        cls._validate_action(for_action)
        runtime = cls._runtime_identity()
        state = await cls._load(session, runtime=runtime, for_update=False)
        reviewed = cls._build_plan(runtime=runtime, state=state, for_action=for_action)
        return {
            **reviewed,
            "plan_token": LegacyOwnerPlanToken.issue(plan_digest=reviewed["plan_digest"]),
            "plan_token_max_age_seconds": LegacyOwnerPlanToken.MAX_AGE_SECONDS,
        }

    @classmethod
    async def execute(
        cls,
        session: AsyncSession,
        *,
        plan_token: str,
        new_password: str,
    ) -> dict[str, Any]:
        try:
            CredentialService.validate_password(new_password)
        except CredentialPolicyError as exc:
            raise LegacyOwnerCutoverBlockedError(
                "One-time credential violates the reviewed password policy"
            ) from exc
        verified = LegacyOwnerPlanToken.verify(plan_token)
        runtime = cls._runtime_identity()
        if not await cls._try_acquire_advisory_lock(session):
            raise LegacyOwnerCutoverBlockedError("Another legacy-owner operation owns the lock")
        state = await cls._load(session, runtime=runtime, for_update=True)
        reviewed = cls._build_plan(runtime=runtime, state=state, for_action="cutover")
        cls._validate_review(verified=verified, reviewed=reviewed)

        auth_state = cls._require_auth_state(state)
        changed = False
        user = state.user
        membership = state.membership
        if auth_state.mode == LegacyOwnerAuthStateService.MODE_LEGACY:
            encoded = await asyncio.to_thread(
                CredentialService.hash_password, new_password
            )
            if user is None:
                tenant, _ = cls._require_scope(state)
                user = StaffUser(
                    display_name=cls.CREATED_DISPLAY_NAME,
                    status=StaffUserService.STATUS_ACTIVE,
                    primary_role=StaffUserService.ROLE_OWNER,
                    roles=[StaffUserService.ROLE_OWNER],
                    username=runtime.normalized_name,
                    password_hash=encoded,
                    auth_version=1,
                    password_changed_at=datetime.now(timezone.utc),
                    must_change_password=False,
                )
                session.add(user)
                await session.flush()
                membership = TenantMembership(
                    tenant_id=int(tenant.id),
                    staff_user_id=int(user.id),
                    role=StaffUserService.ROLE_OWNER,
                    status="active",
                )
                session.add(membership)
                await session.flush()
            else:
                user.password_hash = encoded
                user.password_changed_at = datetime.now(timezone.utc)
                user.must_change_password = False
                user.auth_version = int(user.auth_version) + 1
                session.add(user)
            auth_state.mode = LegacyOwnerAuthStateService.MODE_STAFF_SHADOW
            auth_state.owner_staff_user_id = int(user.id)
            auth_state.legacy_token_version += 1
            auth_state.updated_at = datetime.now(timezone.utc)
            session.add(auth_state)
            await session.flush()
            cls._add_audit(
                session,
                state=state,
                staff_user=user,
                membership=membership,
                plan_token=plan_token,
                action=cls.CUTOVER_AUDIT_ACTION,
            )
            changed = True

        await session.flush()
        after = await cls._load(session, runtime=runtime, for_update=False)
        await cls._assert_exact_after(
            after,
            expected_mode=LegacyOwnerAuthStateService.MODE_STAFF_SHADOW,
            staff_credential=new_password,
        )
        return cls._mutation_result(
            mode="execute",
            changed=changed,
            state=after,
            plan_digest=reviewed["plan_digest"],
        )

    @classmethod
    async def rollback(cls, session: AsyncSession, *, plan_token: str) -> dict[str, Any]:
        verified = LegacyOwnerPlanToken.verify(plan_token)
        runtime = cls._runtime_identity()
        if not await cls._try_acquire_advisory_lock(session):
            raise LegacyOwnerCutoverBlockedError("Another legacy-owner operation owns the lock")
        state = await cls._load(session, runtime=runtime, for_update=True)
        reviewed = cls._build_plan(runtime=runtime, state=state, for_action="rollback")
        cls._validate_review(verified=verified, reviewed=reviewed)

        auth_state = cls._require_auth_state(state)
        changed = False
        if auth_state.mode == LegacyOwnerAuthStateService.MODE_STAFF_SHADOW:
            user = state.user
            membership = state.membership
            if user is None or membership is None:
                raise LegacyOwnerCutoverBlockedError("Bound owner is unavailable")
            user.auth_version = int(user.auth_version) + 1
            session.add(user)
            auth_state.mode = LegacyOwnerAuthStateService.MODE_LEGACY
            auth_state.legacy_token_version += 1
            auth_state.updated_at = datetime.now(timezone.utc)
            session.add(auth_state)
            await session.flush()
            cls._add_audit(
                session,
                state=state,
                staff_user=user,
                membership=membership,
                plan_token=plan_token,
                action=cls.ROLLBACK_AUDIT_ACTION,
            )
            changed = True

        await session.flush()
        after = await cls._load(session, runtime=runtime, for_update=False)
        await cls._assert_exact_after(
            after, expected_mode=LegacyOwnerAuthStateService.MODE_LEGACY
        )
        return cls._mutation_result(
            mode="rollback",
            changed=changed,
            state=after,
            plan_digest=reviewed["plan_digest"],
        )

    @classmethod
    async def verify(
        cls,
        session: AsyncSession,
        *,
        staff_credential: str | None = None,
        binding_challenge: str,
    ) -> dict[str, Any]:
        runtime = cls._runtime_identity()
        state = await cls._load(session, runtime=runtime, for_update=False)
        blockers = cls._scope_and_runtime_blockers(runtime=runtime, state=state)
        auth_state = state.auth_state
        staff_mode = bool(auth_state and auth_state.mode in {
            LegacyOwnerAuthStateService.MODE_STAFF_SHADOW,
            LegacyOwnerAuthStateService.MODE_STAFF,
        })
        legacy_mode = bool(
            auth_state and auth_state.mode == LegacyOwnerAuthStateService.MODE_LEGACY
        )
        credential_matches = False
        if staff_mode:
            blockers.extend(cls._exact_identity_blockers(runtime=runtime, state=state))
            credential_matches = bool(
                staff_credential
                and state.user
                and await CredentialService.verify_password_async(
                    staff_credential, state.user.password_hash
                )
            )
            if not credential_matches:
                blockers.append("staff_credential_unproved")
        elif legacy_mode and auth_state and auth_state.owner_staff_user_id is not None:
            blockers.extend(
                cls._exact_identity_blockers(
                    runtime=runtime,
                    state=state,
                )
            )
        elif legacy_mode and state.candidates:
            blockers.append("unreviewed_existing_identity_collision")
        elif not legacy_mode:
            blockers.append("auth_state_invalid")
        public_blockers = cls._deduplicate(blockers)
        ready = (staff_mode or legacy_mode) and not public_blockers
        reported_credential_ready = (
            credential_matches
            if staff_mode
            else bool(
                legacy_mode
                and runtime.normalized_name
                and runtime.identity_canonical
                and runtime.credential
            )
        )
        return {
            "mode": "verify",
            "ready": ready,
            "blockers": public_blockers,
            "staff_user_id": int(state.user.id) if state.user and state.user.id else None,
            "membership_id": int(state.membership.id) if state.membership and state.membership.id else None,
            "system_tenant_id": int(state.tenant.id) if state.tenant and state.tenant.id else None,
            "system_storefront_id": int(state.storefront.id) if state.storefront and state.storefront.id else None,
            "auth_mode": auth_state.mode if auth_state else "unavailable",
            "legacy_token_version": int(auth_state.legacy_token_version) if auth_state else 0,
            "runtime_binding": LegacyOwnerRuntimeCredential.bind(
                runtime,
                challenge=binding_challenge,
            ),
            "credential_matches": reported_credential_ready,
            "can_change_password": bool(staff_mode and state.user and state.user.password_hash),
            "auth_source_staff_password": bool(ready and staff_mode),
            "legacy_jwt_rejected": bool(ready and staff_mode),
            "legacy_google_auth_rejected": bool(ready and staff_mode),
        }

    @classmethod
    async def _load(
        cls,
        session: AsyncSession,
        *,
        runtime: _RuntimeIdentity,
        for_update: bool,
    ) -> _CutoverState:
        auth_statement = select(LegacyOwnerAuthState).where(
            LegacyOwnerAuthState.id == LegacyOwnerAuthStateService.SINGLETON_ID
        )
        if for_update:
            auth_statement = auth_statement.with_for_update(of=LegacyOwnerAuthState)
        auth_state = (await session.execute(auth_statement)).scalar_one_or_none()

        tenant_statement = select(Tenant).where(func.lower(Tenant.slug) == cls.SYSTEM_TENANT_SLUG)
        if for_update:
            tenant_statement = tenant_statement.with_for_update(of=Tenant)
        tenants = list((await session.execute(tenant_statement)).scalars().all())

        storefronts: list[Storefront] = []
        if len(tenants) == 1 and tenants[0].id is not None:
            statement = select(Storefront).where(
                Storefront.tenant_id == tenants[0].id,
                func.lower(Storefront.slug) == cls.SYSTEM_STOREFRONT_SLUG,
            )
            if for_update:
                statement = statement.with_for_update(of=Storefront)
            storefronts = list((await session.execute(statement)).scalars().all())

        candidates: list[StaffUser] = []
        if runtime.normalized_name:
            statement = (
                select(StaffUser)
                .where(func.lower(StaffUser.username) == runtime.normalized_name)
                .order_by(StaffUser.id.asc())
            )
            if for_update:
                statement = statement.with_for_update(of=StaffUser)
            candidates = list((await session.execute(statement)).scalars().all())

        memberships: list[TenantMembership] = []
        if len(candidates) == 1 and candidates[0].id is not None:
            statement = (
                select(TenantMembership)
                .where(TenantMembership.staff_user_id == candidates[0].id)
                .order_by(TenantMembership.id.asc())
            )
            if for_update:
                statement = statement.with_for_update(of=TenantMembership)
            memberships = list((await session.execute(statement)).scalars().all())
        return _CutoverState(
            auth_state=auth_state,
            tenants=tenants,
            storefronts=storefronts,
            candidates=candidates,
            memberships=memberships,
        )

    @classmethod
    def _build_plan(
        cls,
        *,
        runtime: _RuntimeIdentity,
        state: _CutoverState,
        for_action: PlanAction,
    ) -> dict[str, Any]:
        blockers = cls._plan_blockers(runtime=runtime, state=state, for_action=for_action)
        changes: list[str] = []
        if not blockers:
            auth_state = cls._require_auth_state(state)
            if for_action == "cutover" and auth_state.mode == LegacyOwnerAuthStateService.MODE_LEGACY:
                if state.user is None:
                    changes.extend([
                        "create_staff_user",
                        "create_active_owner_membership",
                        "activate_staff_shadow",
                    ])
                else:
                    changes.append("activate_staff_shadow")
            elif for_action == "rollback" and auth_state.mode == LegacyOwnerAuthStateService.MODE_STAFF_SHADOW:
                changes.append("restore_legacy_auth")
        current = cls._public_state(runtime=runtime, state=state)
        digest_payload = {
            "version": 3,
            "for_action": for_action,
            "runtime_binding": runtime.binding,
            "current": current,
            "blockers": blockers,
            "changes": changes,
        }
        encoded = json.dumps(
            digest_payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        return {
            "mode": "plan",
            "ready": not blockers,
            "target": {
                "system_tenant_slug": cls.SYSTEM_TENANT_SLUG,
                "system_storefront_slug": cls.SYSTEM_STOREFRONT_SLUG,
            },
            "current": current,
            "blockers": blockers,
            "changes": changes,
            "plan_digest": hashlib.sha256(encoded).hexdigest(),
        }

    @classmethod
    def _plan_blockers(
        cls,
        *,
        runtime: _RuntimeIdentity,
        state: _CutoverState,
        for_action: PlanAction,
    ) -> list[str]:
        blockers = cls._scope_and_runtime_blockers(runtime=runtime, state=state)
        auth_state = state.auth_state
        if auth_state is None:
            blockers.append("auth_state_unavailable")
            return blockers
        if auth_state.mode not in LegacyOwnerAuthStateService.MODES:
            blockers.append("auth_state_invalid")
            return blockers

        if for_action == "cutover":
            if auth_state.mode == LegacyOwnerAuthStateService.MODE_STAFF:
                blockers.append("legacy_auth_already_retired")
            elif auth_state.mode == LegacyOwnerAuthStateService.MODE_STAFF_SHADOW:
                blockers.extend(cls._exact_identity_blockers(runtime=runtime, state=state))
            elif state.user is None:
                if auth_state.owner_staff_user_id is not None:
                    blockers.append("bound_owner_unavailable")
            else:
                if auth_state.owner_staff_user_id != state.user.id:
                    blockers.append("unreviewed_existing_identity_collision")
                blockers.extend(cls._exact_identity_blockers(runtime=runtime, state=state))
        else:
            if auth_state.mode == LegacyOwnerAuthStateService.MODE_STAFF:
                blockers.append("retired_legacy_auth_cannot_be_rolled_back")
            elif auth_state.mode == LegacyOwnerAuthStateService.MODE_STAFF_SHADOW:
                blockers.extend(
                    cls._exact_identity_blockers(
                        runtime=runtime,
                        state=state,
                    )
                )
            elif auth_state.owner_staff_user_id is None:
                blockers.append("no_shadow_cutover_to_roll_back")
            else:
                blockers.extend(
                    cls._exact_identity_blockers(
                        runtime=runtime,
                        state=state,
                    )
                )
        return cls._deduplicate(blockers)

    @classmethod
    def _scope_and_runtime_blockers(
        cls, *, runtime: _RuntimeIdentity, state: _CutoverState
    ) -> list[str]:
        blockers: list[str] = []
        if runtime.normalized_name is None:
            blockers.append("runtime_identity_missing")
        if not runtime.identity_canonical:
            blockers.append("runtime_identity_not_canonical")
        if not runtime.credential:
            blockers.append("runtime_credential_missing")
        tenant = state.tenant
        storefront = state.storefront
        if len(state.tenants) != 1:
            blockers.append("canonical_system_tenant_not_unique")
        elif not (
            tenant
            and tenant.slug == cls.SYSTEM_TENANT_SLUG
            and tenant.status == "active"
            and tenant.is_system
        ):
            blockers.append("canonical_system_tenant_not_exact")
        if len(state.storefronts) != 1:
            blockers.append("canonical_system_storefront_not_unique")
        elif not (
            storefront
            and tenant
            and storefront.slug == cls.SYSTEM_STOREFRONT_SLUG
            and storefront.tenant_id == tenant.id
            and storefront.status == "active"
            and storefront.is_default
        ):
            blockers.append("canonical_system_storefront_not_exact")
        if len(state.candidates) > 1:
            blockers.append("staff_identity_collision")
        return blockers

    @classmethod
    def _exact_identity_blockers(
        cls,
        *,
        runtime: _RuntimeIdentity,
        state: _CutoverState,
    ) -> list[str]:
        auth_state = state.auth_state
        user = state.user
        membership = state.membership
        tenant = state.tenant
        if user is None:
            return ["bound_owner_unavailable"]
        blockers: list[str] = []
        if auth_state is None or auth_state.owner_staff_user_id != user.id:
            blockers.append("bound_owner_mismatch")
        if not (
            user.username == runtime.normalized_name
            and user.status == StaffUserService.STATUS_ACTIVE
            and StaffUserService.primary_role(user) == StaffUserService.ROLE_OWNER
            and StaffUserService.normalize_roles(user.roles) == [StaffUserService.ROLE_OWNER]
            and user.legacy_installer_id is None
            and user.telegram_id is None
            and not user.telegram_username
            and user.auth_version >= 1
            and user.password_changed_at is not None
            and not user.must_change_password
        ):
            blockers.append("existing_staff_identity_not_exact")
        if len(state.memberships) != 1:
            blockers.append("shared_or_incomplete_tenant_identity")
        elif not (
            tenant
            and membership
            and membership.tenant_id == tenant.id
            and membership.role == StaffUserService.ROLE_OWNER
            and membership.status == "active"
        ):
            blockers.append("owner_membership_not_exact")
        return blockers

    @classmethod
    def _public_state(
        cls, *, runtime: _RuntimeIdentity, state: _CutoverState
    ) -> dict[str, Any]:
        auth_state = state.auth_state
        user = state.user
        membership = state.membership
        tenant = state.tenant
        storefront = state.storefront
        return {
            "system_tenant_id": int(tenant.id) if tenant and tenant.id else None,
            "system_storefront_id": int(storefront.id) if storefront and storefront.id else None,
            "auth_mode": auth_state.mode if auth_state else "unavailable",
            "legacy_token_version": int(auth_state.legacy_token_version) if auth_state else 0,
            "bound_staff_user_id": int(auth_state.owner_staff_user_id) if auth_state and auth_state.owner_staff_user_id else None,
            "candidate_count": len(state.candidates),
            "staff_user_id": int(user.id) if user and user.id else None,
            "auth_version": int(user.auth_version) if user else None,
            "membership_count": len(state.memberships),
            "membership_id": int(membership.id) if membership and membership.id else None,
            "active": bool(user and user.status == StaffUserService.STATUS_ACTIVE),
            "owner_role": bool(
                user
                and StaffUserService.primary_role(user) == StaffUserService.ROLE_OWNER
                and StaffUserService.normalize_roles(user.roles) == [StaffUserService.ROLE_OWNER]
            ),
            "normalized_identity_exact": bool(user and user.username == runtime.normalized_name),
            "credential_timestamp_set": bool(user and user.password_changed_at),
            "forced_change_disabled": bool(user) and not user.must_change_password,
            "membership_exact": bool(
                membership
                and tenant
                and membership.tenant_id == tenant.id
                and membership.role == StaffUserService.ROLE_OWNER
                and membership.status == "active"
            ),
        }

    @classmethod
    def _runtime_identity(cls) -> _RuntimeIdentity:
        return LegacyOwnerRuntimeCredential.load()

    @classmethod
    async def _try_acquire_advisory_lock(cls, session: AsyncSession) -> bool:
        if session.get_bind().dialect.name != "postgresql":
            raise LegacyOwnerCutoverBlockedError("Legacy-owner cutover requires PostgreSQL")
        return bool(
            await session.scalar(
                text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": cls.LOCK_KEY},
            )
        )

    @classmethod
    def _add_audit(
        cls,
        session: AsyncSession,
        *,
        state: _CutoverState,
        staff_user: StaffUser,
        membership: TenantMembership | None,
        plan_token: str,
        action: str,
    ) -> None:
        tenant, storefront = cls._require_scope(state)
        if staff_user.id is None or membership is None or membership.id is None:
            raise LegacyOwnerCutoverBlockedError("Cutover audit target is incomplete")
        request_id = "legacy-owner-" + hashlib.sha256(plan_token.encode("utf-8")).hexdigest()[:32]
        session.add(
            TenantAuditEvent(
                tenant_id=int(tenant.id),
                storefront_id=int(storefront.id),
                actor_staff_user_id=None,
                actor_username=cls.AUDIT_ACTOR,
                action=action,
                entity_type="staff_user",
                entity_id=int(staff_user.id),
                request_id=request_id,
                change_set={
                    "staff_user_id": int(staff_user.id),
                    "membership_id": int(membership.id),
                    "active": True,
                    "owner_role": True,
                    "staff_shadow_enabled": action == cls.CUTOVER_AUDIT_ACTION,
                    "legacy_auth_enabled": action == cls.ROLLBACK_AUDIT_ACTION,
                },
            )
        )

    @classmethod
    def _mutation_result(
        cls,
        *,
        mode: Literal["execute", "rollback"],
        changed: bool,
        state: _CutoverState,
        plan_digest: str,
    ) -> dict[str, Any]:
        auth_state = cls._require_auth_state(state)
        tenant, storefront = cls._require_scope(state)
        if state.user is None or state.membership is None:
            raise LegacyOwnerCutoverBlockedError("Bound owner is unavailable")
        return {
            "mode": mode,
            "ready": True,
            "changed": changed,
            "staff_user_id": int(state.user.id),
            "membership_id": int(state.membership.id),
            "system_tenant_id": int(tenant.id),
            "system_storefront_id": int(storefront.id),
            "auth_mode": auth_state.mode,
            "legacy_token_version": int(auth_state.legacy_token_version),
            "plan_digest": plan_digest,
        }

    @classmethod
    def _validate_review(
        cls, *, verified: VerifiedLegacyOwnerPlanToken, reviewed: dict[str, Any]
    ) -> None:
        if not hmac.compare_digest(verified.plan_digest, reviewed["plan_digest"]):
            raise LegacyOwnerCutoverBlockedError("Cutover plan token is stale; run a fresh plan")
        if reviewed["blockers"]:
            raise LegacyOwnerCutoverBlockedError("Legacy-owner operation preflight is blocked")

    @classmethod
    async def _assert_exact_after(
        cls,
        state: _CutoverState,
        *,
        expected_mode: str,
        staff_credential: str | None = None,
    ) -> None:
        runtime = cls._runtime_identity()
        blockers = cls._scope_and_runtime_blockers(runtime=runtime, state=state)
        blockers.extend(
            cls._exact_identity_blockers(
                runtime=runtime,
                state=state,
            )
        )
        if expected_mode != LegacyOwnerAuthStateService.MODE_LEGACY:
            if not (
                staff_credential
                and state.user
                and await CredentialService.verify_password_async(
                    staff_credential, state.user.password_hash
                )
            ):
                blockers.append("staff_credential_unproved")
        if state.auth_state is None or state.auth_state.mode != expected_mode:
            blockers.append("auth_mode_not_reached")
        if cls._deduplicate(blockers):
            raise LegacyOwnerCutoverBlockedError(
                "Operation post-check did not reach the reviewed target state"
            )

    @staticmethod
    def _validate_action(for_action: str) -> None:
        if for_action not in {"cutover", "rollback"}:
            raise ValueError("Plan action is invalid")

    @staticmethod
    def _require_auth_state(state: _CutoverState) -> LegacyOwnerAuthState:
        if state.auth_state is None:
            raise LegacyOwnerCutoverBlockedError("Legacy-owner authentication state is unavailable")
        return state.auth_state

    @staticmethod
    def _require_scope(state: _CutoverState) -> tuple[Tenant, Storefront]:
        if state.tenant is None or state.storefront is None:
            raise LegacyOwnerCutoverBlockedError("Canonical system scope is unavailable")
        return state.tenant, state.storefront

    @staticmethod
    def _deduplicate(values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))

__all__ = [
    "LegacyOwnerCutoverBlockedError",
    "LegacyOwnerCutoverService",
]
