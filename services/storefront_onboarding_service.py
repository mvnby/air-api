from __future__ import annotations

import hashlib
import hmac
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from crud.storefront_onboarding import StorefrontOnboardingDAO
from services.storefront_onboarding_manifest import StorefrontOnboardingManifest
from services.storefront_onboarding_plan_token import StorefrontOnboardingPlanToken
from services.storefront_onboarding_planner import StorefrontOnboardingPlanner
from services.storefront_onboarding_staging import (
    StorefrontOnboardingStagingService,
)
from services.storefront_onboarding_state import (
    StorefrontOnboardingBlockedError,
    serialize_state,
)


class StorefrontOnboardingService:
    """Fresh-plan guarded tenant/storefront onboarding lifecycle boundary."""

    @classmethod
    async def status(
        cls,
        session: AsyncSession,
        *,
        hostname: str,
        manifest: StorefrontOnboardingManifest,
    ) -> dict[str, Any]:
        normalized_hostname = manifest.normalize_selected_hostname(hostname)
        state = await StorefrontOnboardingPlanner.load_state(
            session,
            hostname=normalized_hostname,
            manifest=manifest,
            resolve_manifest_offers=False,
            for_update=False,
        )
        blockers = StorefrontOnboardingPlanner.base_blockers(
            state,
            manifest=manifest,
            hostname=normalized_hostname,
        )
        return {
            "mode": "status",
            "tenant_slug": manifest.tenant.slug,
            "storefront_slug": manifest.storefront.slug,
            "hostname": normalized_hostname,
            "manifest_fingerprint": manifest.fingerprint,
            "ownership_safe": not blockers,
            "blockers": blockers,
            "state": serialize_state(state),
        }

    @classmethod
    async def plan(
        cls,
        session: AsyncSession,
        *,
        action: str,
        hostname: str,
        manifest: StorefrontOnboardingManifest,
    ) -> dict[str, Any]:
        plan, _ = await StorefrontOnboardingPlanner.build(
            session,
            action=action,
            hostname=hostname,
            manifest=manifest,
            for_update=False,
        )
        plan_token = StorefrontOnboardingPlanToken.issue(
            plan_digest=plan["plan_digest"]
        )
        return {
            **plan,
            "plan_token": plan_token,
            "plan_token_max_age_seconds": (
                StorefrontOnboardingPlanToken.MAX_AGE_SECONDS
            ),
        }

    @classmethod
    async def execute(
        cls,
        session: AsyncSession,
        *,
        action: str,
        hostname: str,
        manifest: StorefrontOnboardingManifest,
        plan_token: str,
    ) -> dict[str, Any]:
        verified_token = StorefrontOnboardingPlanToken.verify(plan_token)
        normalized_hostname = manifest.normalize_selected_hostname(hostname)
        if not await StorefrontOnboardingDAO.try_acquire_transaction_locks(
            session,
            tenant_slug=manifest.tenant.slug,
            storefront_slug=manifest.storefront.slug,
            hostname=normalized_hostname,
        ):
            raise StorefrontOnboardingBlockedError(
                "Another onboarding transaction owns this storefront or hostname"
            )

        reviewed, state = await StorefrontOnboardingPlanner.build(
            session,
            action=action,
            hostname=normalized_hostname,
            manifest=manifest,
            for_update=True,
        )
        if not hmac.compare_digest(
            verified_token.plan_digest, reviewed["plan_digest"]
        ):
            raise StorefrontOnboardingBlockedError(
                "Onboarding plan token is stale; run a fresh plan"
            )
        if reviewed["blockers"]:
            raise StorefrontOnboardingBlockedError(
                "Storefront onboarding preflight is blocked: "
                + "; ".join(reviewed["blockers"])
            )

        request_id = "onboarding-" + hashlib.sha256(
            plan_token.encode("utf-8")
        ).hexdigest()[:32]
        changed, invalidation_staged = (
            await StorefrontOnboardingStagingService.stage(
                session,
                action=reviewed["action"],
                hostname=reviewed["hostname"],
                manifest=manifest,
                state=state,
                request_id=request_id,
            )
        )
        await session.flush()

        after, _ = await StorefrontOnboardingPlanner.build(
            session,
            action=reviewed["action"],
            hostname=reviewed["hostname"],
            manifest=manifest,
            for_update=False,
        )
        if after["blockers"] or after["changes"]:
            raise StorefrontOnboardingBlockedError(
                "Storefront onboarding post-check did not reach the reviewed target state"
            )
        reviewed_without_digest = {
            key: value
            for key, value in reviewed.items()
            if key not in {"plan_digest"}
        }
        return {
            **reviewed_without_digest,
            "mode": "execute",
            "changed_entities": changed,
            "catalog_invalidation_staged": invalidation_staged,
            "after": after["state"],
        }


__all__ = [
    "StorefrontOnboardingBlockedError",
    "StorefrontOnboardingService",
]
