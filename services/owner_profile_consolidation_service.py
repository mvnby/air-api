"""Reviewed one-time 1 -> 4 profile consolidation; never rewrite business FKs.

The caller owns the transaction. Only the fixed, already bound owner receives
the personal profile; its credential, auth version and company grants survive.
"""

from datetime import datetime, timezone
import hashlib
import hmac
import json

from sqlalchemy import func
from sqlmodel import SQLModel, select

from models import Installer, LegacyOwnerAuthState, StaffUser, Storefront, Tenant, TenantAuditEvent, TenantMembership
from services.legacy_owner_cutover_plan import LegacyOwnerPlanToken
from services.legacy_owner_cutover_service import LegacyOwnerCutoverService, LegacyOwnerCutoverBlockedError
from services.legacy_owner_profile_policy import LegacyOwnerProfilePolicy
from services.legacy_owner_runtime_credential import LegacyOwnerRuntimeCredential


class OwnerProfileConsolidationService:
    SOURCE_ID = 1
    TARGET_ID = 4
    ACTION = "owner_profile.consolidated"
    # These are retained history or the explicitly moved profile. Every other
    # source FK blocks, including newly introduced application tables.
    RETAINED_TABLES = frozenset({
        "tenant_membership", "staff_avatar", "tenant_audit_event",
        "command_audit", "connector_auth_event", "staff_telegram_retired_identity",
    })

    @classmethod
    async def _load(cls, session, *, lock=False):
        async def rows(model, predicate, order):
            query = select(model).where(predicate).order_by(order).execution_options(populate_existing=True)
            if lock:
                query = query.with_for_update().execution_options(populate_existing=True)
            return list((await session.execute(query)).scalars())

        states = await rows(LegacyOwnerAuthState, LegacyOwnerAuthState.id == 1, LegacyOwnerAuthState.id)
        tenants = await rows(Tenant, Tenant.slug == "mvn", Tenant.id)
        users = await rows(StaffUser, StaffUser.id.in_([cls.SOURCE_ID, cls.TARGET_ID]), StaffUser.id)
        memberships = await rows(TenantMembership, TenantMembership.staff_user_id.in_([cls.SOURCE_ID, cls.TARGET_ID]), TenantMembership.id)
        installer_ids = [user.legacy_installer_id for user in users if user.legacy_installer_id is not None]
        installers = await rows(Installer, Installer.id.in_(installer_ids), Installer.id)
        from models.staff_avatar import StaffAvatar
        avatars = await rows(StaffAvatar, StaffAvatar.staff_user_id.in_([cls.SOURCE_ID, cls.TARGET_ID]), StaffAvatar.staff_user_id)
        storefronts = list((await session.execute(select(Storefront).where(
            Storefront.tenant_id.in_([tenant.id for tenant in tenants]),
            Storefront.slug == "main", Storefront.is_default.is_(True),
        ).execution_options(populate_existing=True))).scalars())
        references = {}
        for table in sorted(SQLModel.metadata.tables.values(), key=lambda item: item.name):
            for column in table.columns:
                if any(fk.target_fullname == "staff_users.id" for fk in column.foreign_keys):
                    count = int(await session.scalar(select(func.count()).select_from(table).where(column == cls.SOURCE_ID)) or 0)
                    if count:
                        references[f"{table.name}.{column.name}"] = count
        return {
            "state": states[0] if len(states) == 1 else None,
            "tenant": tenants[0] if len(tenants) == 1 else None,
            "storefront": storefronts[0] if len(storefronts) == 1 else None,
            "users": {user.id: user for user in users}, "memberships": memberships,
            "installers": {item.id: item for item in installers},
            "avatars": {item.staff_user_id: item for item in avatars}, "references": references,
        }

    @classmethod
    def _review(cls, data):
        runtime = LegacyOwnerRuntimeCredential.load()
        source, target = (data["users"].get(key) for key in (cls.SOURCE_ID, cls.TARGET_ID))
        state, tenant, storefront = (data[key] for key in ("state", "tenant", "storefront"))
        blockers = []
        if not runtime.identity_canonical or not runtime.credential or not runtime.normalized_name:
            blockers.append("recovery_credential_unavailable")
        if state is None or state.mode != "staff_shadow" or state.owner_staff_user_id != cls.TARGET_ID:
            blockers.append("bound_shadow_owner_not_exact")
        if tenant is None or not tenant.is_system or tenant.status != "active":
            blockers.append("system_company_not_exact")
        if storefront is None or storefront.status != "active":
            blockers.append("system_storefront_not_exact")
        if source is None or target is None:
            blockers.append("reviewed_accounts_missing")
        complete = bool(source and source.merged_into_staff_user_id == cls.TARGET_ID)
        if source and target:
            if target.username != runtime.normalized_name or not target.password_hash or target.must_change_password:
                blockers.append("canonical_credential_not_exact")
            if not LegacyOwnerProfilePolicy.allows(target, installer=data["installers"].get(target.legacy_installer_id)):
                blockers.append("canonical_owner_profile_invalid")
            if complete:
                if source.status != "inactive" or source.telegram_id is not None or source.legacy_installer_id is not None:
                    blockers.append("retired_source_not_exact")
            else:
                if (
                    source.status != "active" or source.primary_role != "owner"
                    or set(source.roles) != {"owner", "installer"}
                    or source.username is not None or source.password_hash is not None
                    or source.merged_into_staff_user_id is not None
                    or source.telegram_id is None or source.legacy_installer_id is None
                ):
                    blockers.append("source_profile_not_exact")
                installer = data["installers"].get(source.legacy_installer_id)
                if installer is None or installer.telegram_id != source.telegram_id:
                    blockers.append("source_installer_not_exact")
                if target.telegram_id is not None or target.legacy_installer_id is not None:
                    blockers.append("target_profile_already_linked")
                if cls.SOURCE_ID in data["avatars"] and cls.TARGET_ID in data["avatars"]:
                    blockers.append("avatar_choice_required")
            for user_id in (cls.SOURCE_ID, cls.TARGET_ID):
                memberships = [item for item in data["memberships"] if item.staff_user_id == user_id]
                expected_status = "disabled" if complete and user_id == cls.SOURCE_ID else "active"
                if (len(memberships) != 1 or tenant is None
                    or memberships[0].tenant_id != tenant.id
                    or memberships[0].role != "owner" or memberships[0].status != expected_status):
                    blockers.append("membership_not_exact")
                if user_id == cls.SOURCE_ID and any(item.permissions for item in memberships):
                    blockers.append("source_permissions_require_review")
        unexplained = {key: count for key, count in data["references"].items()
                       if key.split(".")[0] not in cls.RETAINED_TABLES}
        if unexplained:
            blockers.append("source_references_require_review")
        # Exact row values, including secret credential state, are digested only
        # inside this process. Neither the snapshot nor runtime binding is public.
        def snapshot(row):
            return row.model_dump(mode="python") if row is not None else None
        private = {
            "operation": "owner-profile-consolidation-v1", "runtime": runtime.binding,
            "state": snapshot(state), "tenant": snapshot(tenant), "storefront": snapshot(storefront),
            "users": [snapshot(data["users"][key]) for key in sorted(data["users"])],
            "memberships": [snapshot(item) for item in data["memberships"]],
            "installers": [snapshot(item) for item in data["installers"].values()],
            "avatars": {str(key): {"content_digest": hashlib.sha256(item.content).hexdigest(),
                                    "updated_at": item.updated_at} for key, item in data["avatars"].items()},
            "references": data["references"],
        }
        def canonical_value(value):
            if isinstance(value, datetime):
                return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.astimezone(timezone.utc).isoformat()
            raise TypeError("Unsupported reviewed snapshot value")
        digest = hashlib.sha256(json.dumps(private, sort_keys=True, separators=(",", ":"), default=canonical_value).encode()).hexdigest()
        return {
            "mode": "plan", "ready": not blockers, "complete": complete,
            "source_staff_user_id": cls.SOURCE_ID, "target_staff_user_id": cls.TARGET_ID,
            "blockers": sorted(set(blockers)), "source_references": data["references"],
            "changes": [] if complete else ["transfer_personal_profile", "retire_source_account", "preserve_owner_sessions_and_business_links"],
            "preserve_target_auth_version": True, "plan_digest": digest,
        }

    @classmethod
    async def plan(cls, session):
        result = cls._review(await cls._load(session))
        return {**result, "plan_token": LegacyOwnerPlanToken.issue(plan_digest=result["plan_digest"])}

    @classmethod
    async def execute(cls, session, *, plan_token):
        verified = LegacyOwnerPlanToken.verify(plan_token)
        if not await LegacyOwnerCutoverService._try_acquire_advisory_lock(session):
            raise LegacyOwnerCutoverBlockedError("Another owner operation owns the lock")
        data = await cls._load(session, lock=True)
        reviewed = cls._review(data)
        if not hmac.compare_digest(verified.plan_digest, reviewed["plan_digest"]):
            raise LegacyOwnerCutoverBlockedError("Consolidation plan is stale; review a fresh plan")
        if not reviewed["ready"]:
            raise LegacyOwnerCutoverBlockedError("Consolidation preflight is blocked")
        if reviewed["complete"]:
            return {**reviewed, "mode": "execute", "changed": False}
        source, target = (data["users"][key] for key in (cls.SOURCE_ID, cls.TARGET_ID))
        now = datetime.now(timezone.utc)
        original_credential = (target.username, target.password_hash, target.auth_version)
        source_previous_version = source.auth_version
        previous_notification_consent = target.telegram_notifications_enabled
        telegram_id, telegram_username, installer_id = source.telegram_id, source.telegram_username, source.legacy_installer_id
        source.telegram_id = None
        source.telegram_username = None
        source.telegram_verified_at = None
        source.legacy_installer_id = None
        source.status = "inactive"
        source.auth_version += 1
        source.merged_into_staff_user_id = target.id
        for membership in data["memberships"]:
            if membership.staff_user_id == source.id:
                membership.status = "disabled"
                membership.updated_at = now
        # Release unique Telegram and installer keys before their reassignment.
        await session.flush()
        target.telegram_id, target.telegram_username = telegram_id, telegram_username
        target.telegram_verified_at = now
        target.telegram_notifications_enabled = bool(
            target.telegram_notifications_enabled and source.telegram_notifications_enabled
        )
        target.legacy_installer_id = installer_id
        target.roles = ["owner", "installer"]
        target.display_name = source.display_name
        for field in ("phone", "email", "default_rate"):
            if getattr(target, field) in (None, ""):
                setattr(target, field, getattr(source, field))
        if source.id in data["avatars"]:
            avatar = data["avatars"][source.id]
            avatar.staff_user_id = target.id
            target.avatar_version = avatar.content_hash
            source.avatar_version = None
        session.add(TenantAuditEvent(
            tenant_id=data["tenant"].id, storefront_id=data["storefront"].id,
            actor_staff_user_id=target.id, actor_username="system:owner-profile-consolidation",
            action=cls.ACTION, entity_type="staff_user", entity_id=target.id,
            request_id="owner-profile-" + hashlib.sha256(plan_token.encode()).hexdigest()[:32],
            change_set={"source_staff_user_id": source.id, "target_staff_user_id": target.id,
                        "method": "reviewed_owner_consolidation",
                        "source_auth_version": {"before": source_previous_version, "after": source.auth_version},
                        "source_status": {"before": "active", "after": "inactive"},
                        "source_membership_status": {"before": "active", "after": "disabled"},
                        "profile_transferred": {"telegram_id": telegram_id, "installer_id": installer_id},
                        "notification_consent": {"before": previous_notification_consent,
                                                 "after": target.telegram_notifications_enabled},
                        "target_auth_version_preserved": target.auth_version, "historical_foreign_keys_rewritten": False,
                        "plan_digest": reviewed["plan_digest"]},
        ))
        await session.flush()
        after = cls._review(await cls._load(session))
        if not after["ready"] or not after["complete"] or (target.username, target.password_hash, target.auth_version) != original_credential:
            raise LegacyOwnerCutoverBlockedError("Consolidation post-check failed")
        return {**after, "mode": "execute", "changed": True}

    @classmethod
    async def verify(cls, session, *, binding_challenge):
        result = cls._review(await cls._load(session))
        return {**result, "mode": "verify", "runtime_binding": LegacyOwnerRuntimeCredential.bind(
            LegacyOwnerRuntimeCredential.load(), challenge=binding_challenge,
        )}
