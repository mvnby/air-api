from __future__ import annotations

import hmac
import re
from typing import Any, Iterable, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from crud.orsha_storefront_bootstrap import OrshaStorefrontBootstrapDAO
from services.orsha_storefront_bootstrap_planner import (
    OrshaStorefrontBootstrapPlanner,
)
from services.orsha_storefront_bootstrap_state import (
    OrshaStorefrontBootstrapBlockedError,
    OrshaStorefrontDefinition,
    serialize_state,
)
from services.orsha_storefront_lifecycle_staging import (
    OrshaStorefrontLifecycleStagingService,
)
from services.orsha_storefront_manifest import OrshaStorefrontOfferSpec


class OrshaStorefrontBootstrapService:
    """Review-token guarded lifecycle boundary for the internal Orsha canary."""

    TENANT_SLUG = OrshaStorefrontDefinition.TENANT_SLUG
    STOREFRONT_SLUG = OrshaStorefrontDefinition.STOREFRONT_SLUG
    STOREFRONT_DISPLAY_NAME = OrshaStorefrontDefinition.STOREFRONT_DISPLAY_NAME
    STOREFRONT_CITY = OrshaStorefrontDefinition.STOREFRONT_CITY
    DEFAULT_LOCALE = OrshaStorefrontDefinition.DEFAULT_LOCALE
    CURRENCY = OrshaStorefrontDefinition.CURRENCY
    ACTOR_USERNAME = OrshaStorefrontDefinition.ACTOR_USERNAME
    ACTIONS = OrshaStorefrontDefinition.ACTIONS

    @classmethod
    async def status(
        cls,
        session: AsyncSession,
        *,
        hostname: str,
    ) -> dict[str, Any]:
        normalized_hostname = OrshaStorefrontBootstrapPlanner.normalize_hostname(
            hostname
        )
        state = await OrshaStorefrontBootstrapPlanner.load_state(
            session,
            hostname=normalized_hostname,
            offer_specs=(),
            for_update=False,
        )
        blockers = OrshaStorefrontBootstrapPlanner.base_blockers(
            state,
            hostname=normalized_hostname,
        )
        return {
            "mode": "status",
            "tenant_slug": cls.TENANT_SLUG,
            "storefront_slug": cls.STOREFRONT_SLUG,
            "hostname": normalized_hostname,
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
        offer_specs: Iterable[OrshaStorefrontOfferSpec | Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        plan, _ = await OrshaStorefrontBootstrapPlanner.build(
            session,
            action=action,
            hostname=hostname,
            offer_specs=offer_specs,
            for_update=False,
        )
        return plan

    @classmethod
    async def execute(
        cls,
        session: AsyncSession,
        *,
        action: str,
        hostname: str,
        plan_token: str,
        offer_specs: Iterable[OrshaStorefrontOfferSpec | Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        cls._validate_plan_token(plan_token)
        if not await OrshaStorefrontBootstrapDAO.try_acquire_transaction_lock(session):
            raise OrshaStorefrontBootstrapBlockedError(
                "Another Orsha storefront lifecycle transaction is already running"
            )

        reviewed, state = await OrshaStorefrontBootstrapPlanner.build(
            session,
            action=action,
            hostname=hostname,
            offer_specs=offer_specs,
            for_update=True,
        )
        if not hmac.compare_digest(plan_token, reviewed["plan_token"]):
            raise OrshaStorefrontBootstrapBlockedError(
                "Orsha storefront plan token is stale; run a fresh plan"
            )
        if reviewed["blockers"]:
            raise OrshaStorefrontBootstrapBlockedError(
                "Orsha storefront preflight is blocked: "
                + "; ".join(reviewed["blockers"])
            )

        normalized_action = reviewed["action"]
        normalized_hostname = reviewed["hostname"]
        request_id = f"orsha-{normalized_action}-{plan_token[:32]}"
        changed, invalidation_staged = (
            await OrshaStorefrontLifecycleStagingService.stage(
                session,
                action=normalized_action,
                hostname=normalized_hostname,
                state=state,
                request_id=request_id,
            )
        )
        await session.flush()

        after, _ = await OrshaStorefrontBootstrapPlanner.build(
            session,
            action=normalized_action,
            hostname=normalized_hostname,
            offer_specs=offer_specs,
            for_update=False,
        )
        if after["blockers"] or after["changes"]:
            raise OrshaStorefrontBootstrapBlockedError(
                "Orsha storefront post-check did not reach the reviewed target state"
            )
        return {
            **reviewed,
            "mode": "execute",
            "changed_entities": changed,
            "catalog_invalidation_staged": invalidation_staged,
            "after": after["state"],
        }

    @staticmethod
    def _validate_plan_token(plan_token: str) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", str(plan_token or "")):
            raise OrshaStorefrontBootstrapBlockedError(
                "Execute requires the 64-character plan token from a fresh plan"
            )


__all__ = [
    "OrshaStorefrontBootstrapBlockedError",
    "OrshaStorefrontBootstrapService",
]
