from __future__ import annotations

import hashlib
import hmac
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from crud.shared_catalog_grant import SharedCatalogGrantDAO
from services.shared_catalog_grant_manifest import SharedCatalogGrantManifest
from services.shared_catalog_grant_plan_token import SharedCatalogGrantPlanToken
from services.shared_catalog_grant_planner import (
    SharedCatalogGrantBlockedError,
    SharedCatalogGrantPlanner,
)
from services.shared_catalog_grant_staging import (
    SharedCatalogGrantStagingService,
)


class SharedCatalogGrantService:
    @classmethod
    async def plan(
        cls,
        session: AsyncSession,
        *,
        desired_status: str,
        manifest: SharedCatalogGrantManifest,
    ) -> dict[str, Any]:
        plan, _ = await SharedCatalogGrantPlanner.build(
            session,
            desired_status=desired_status,
            manifest=manifest,
            for_update=False,
        )
        return {
            **plan,
            "plan_token": SharedCatalogGrantPlanToken.issue(
                plan_digest=plan["plan_digest"]
            ),
            "plan_token_max_age_seconds": SharedCatalogGrantPlanToken.MAX_AGE_SECONDS,
        }

    @classmethod
    async def execute(
        cls,
        session: AsyncSession,
        *,
        desired_status: str,
        manifest: SharedCatalogGrantManifest,
        plan_token: str,
    ) -> dict[str, Any]:
        verified = SharedCatalogGrantPlanToken.verify(plan_token)
        if not await SharedCatalogGrantDAO.try_acquire_transaction_lock(
            session,
            tenant_slug=manifest.tenant_slug,
            storefront_slug=manifest.storefront_slug,
        ):
            raise SharedCatalogGrantBlockedError(
                "Another shared catalog sync owns this storefront"
            )
        initial, _ = await SharedCatalogGrantPlanner.build(
            session,
            desired_status=desired_status,
            manifest=manifest,
            for_update=True,
        )
        if initial["blockers"]:
            raise SharedCatalogGrantBlockedError(
                "Shared catalog sync is blocked: " + "; ".join(initial["blockers"])
            )
        product_ids = [
            int(change["product_id"]) for change in initial["batch_changes"]
        ]
        scope = initial["scope"]
        assert scope is not None
        await SharedCatalogGrantDAO.lock_products(session, product_ids)
        await SharedCatalogGrantDAO.lock_offers(
            session,
            tenant_id=int(scope["tenant_id"]),
            storefront_id=int(scope["storefront_id"]),
            product_ids=product_ids,
        )
        reviewed, state = await SharedCatalogGrantPlanner.build(
            session,
            desired_status=desired_status,
            manifest=manifest,
            for_update=False,
        )
        if not hmac.compare_digest(
            verified.plan_digest,
            reviewed["plan_digest"],
        ):
            raise SharedCatalogGrantBlockedError(
                "Shared catalog plan is stale; run a fresh plan"
            )
        if reviewed["blockers"]:
            raise SharedCatalogGrantBlockedError(
                "Shared catalog sync is blocked: "
                + "; ".join(reviewed["blockers"])
            )
        request_id = "catalog-grant-" + hashlib.sha256(
            plan_token.encode("utf-8")
        ).hexdigest()[:32]
        staged = await SharedCatalogGrantStagingService.stage(
            session,
            plan=reviewed,
            state=state,
            manifest=manifest,
            request_id=request_id,
        )
        after, _ = await SharedCatalogGrantPlanner.build(
            session,
            desired_status=desired_status,
            manifest=manifest,
            for_update=False,
        )
        grant = staged["grant"]
        return {
            "mode": "execute",
            "desired_status": reviewed["desired_status"],
            "tenant_slug": manifest.tenant_slug,
            "storefront_slug": manifest.storefront_slug,
            "manifest_fingerprint": manifest.fingerprint,
            "reviewed_plan_digest": reviewed["plan_digest"],
            "changed": staged["changed"],
            "offer_changes": staged["offer_changes"],
            "catalog_invalidation_staged": staged[
                "catalog_invalidation_staged"
            ],
            "grant_status": grant.status if grant is not None else None,
            "grant_revision": grant.revision if grant is not None else None,
            "remaining_offer_changes": after["offer_change_count"],
            "complete": (
                not after["blockers"]
                and after["offer_change_count"] == 0
                and after["grant_change"] is None
            ),
            "next_plan_required": bool(
                after["offer_change_count"] or after["grant_change"]
            ),
        }


__all__ = ["SharedCatalogGrantService"]
