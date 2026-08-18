"""Deprecated Orsha planner adapter over generic onboarding planning."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from services.orsha_storefront_bootstrap_service import build_orsha_manifest
from services.orsha_storefront_manifest import OrshaStorefrontOfferSpec
from services.storefront_onboarding_planner import StorefrontOnboardingPlanner


class OrshaStorefrontBootstrapPlanner:
    @staticmethod
    def normalize_hostname(hostname: str) -> str:
        manifest = build_orsha_manifest(
            hostname=hostname,
            offer_specs=(),
            enforce_offer_bounds=False,
        )
        return manifest.normalize_selected_hostname(hostname)

    @classmethod
    async def build(
        cls,
        session: AsyncSession,
        *,
        action: str,
        hostname: str,
        offer_specs: Iterable[OrshaStorefrontOfferSpec | Mapping[str, Any]],
        for_update: bool,
    ):
        return await StorefrontOnboardingPlanner.build(
            session,
            action=action,
            hostname=hostname,
            manifest=build_orsha_manifest(
                hostname=hostname,
                offer_specs=offer_specs,
                enforce_offer_bounds=action in {"bootstrap", "activate"},
            ),
            for_update=for_update,
        )

    @staticmethod
    def base_blockers(state, *, hostname: str):
        manifest = build_orsha_manifest(
            hostname=hostname,
            offer_specs=(),
            enforce_offer_bounds=False,
        )
        blockers = StorefrontOnboardingPlanner.base_blockers(
            state,
            manifest=manifest,
            hostname=manifest.normalize_selected_hostname(hostname),
        )
        compatibility = {
            "storefront has more than one managed domain": (
                "Orsha storefront has more than one domain"
            ),
            "storefront domain is not primary": (
                "Orsha storefront domain is not primary"
            ),
        }
        return [compatibility.get(value, value) for value in blockers]

    @staticmethod
    def _plan_disable(state):
        return StorefrontOnboardingPlanner._plan_disable(
            state,
            manifest=build_orsha_manifest(
                hostname="orsha.mvn.by",
                offer_specs=(),
                enforce_offer_bounds=False,
            ),
        )


__all__ = ["OrshaStorefrontBootstrapPlanner"]
