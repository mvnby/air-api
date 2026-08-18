"""Thin backward-compatible Orsha adapter for generic storefront onboarding."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from services.orsha_storefront_manifest import (
    OrshaStorefrontManifest,
    OrshaStorefrontOfferSpec,
)
from services.storefront_onboarding_manifest import StorefrontOnboardingManifest
from services.storefront_onboarding_service import (
    StorefrontOnboardingBlockedError,
    StorefrontOnboardingService,
)


ORSHA_ALLOWED_HOSTNAMES = frozenset(
    {"orsha-internal.mvn.by", "orsha.mvn.by"}
)
OrshaStorefrontBootstrapBlockedError = StorefrontOnboardingBlockedError


def build_orsha_manifest(
    *,
    hostname: str,
    offer_specs: Iterable[OrshaStorefrontOfferSpec | Mapping[str, Any]],
    enforce_offer_bounds: bool,
) -> StorefrontOnboardingManifest:
    normalized_hostname = str(hostname or "").strip().rstrip(".").casefold()
    if normalized_hostname not in ORSHA_ALLOWED_HOSTNAMES:
        raise ValueError("Orsha hostname is not in the compatibility allowlist")
    raw_offers = [
        value.to_dict() if isinstance(value, OrshaStorefrontOfferSpec) else value
        for value in offer_specs
    ]
    offers = (
        [value.to_dict() for value in OrshaStorefrontManifest.normalize(raw_offers)]
        if enforce_offer_bounds
        else raw_offers
    )
    return StorefrontOnboardingManifest.normalize(
        {
            "version": 1,
            "tenant": {
                "slug": "mvn",
                "display_name": "Мастер Воздуха",
                "kind": "operator",
                "is_system": True,
                "lifecycle": "existing",
            },
            "storefront": {
                "slug": "orsha",
                "display_name": "MVN Орша",
                "city": "Орша",
                "default_locale": "ru-BY",
                "currency": "BYN",
                "is_default": False,
            },
            "allowed_hostnames": [normalized_hostname],
            "offers": offers,
        }
    )


class OrshaStorefrontBootstrapService:
    """Deprecated API adapter; all lifecycle logic lives in the generic service."""

    TENANT_SLUG = "mvn"
    STOREFRONT_SLUG = "orsha"
    STOREFRONT_DISPLAY_NAME = "MVN Орша"
    STOREFRONT_CITY = "Орша"
    DEFAULT_LOCALE = "ru-BY"
    CURRENCY = "BYN"
    ACTOR_USERNAME = "system:storefront-onboarding:mvn:orsha"
    ACTIONS = frozenset({"bootstrap", "verify-domain", "activate", "disable"})

    @classmethod
    async def status(
        cls,
        session: AsyncSession,
        *,
        hostname: str,
    ) -> dict[str, Any]:
        return await StorefrontOnboardingService.status(
            session,
            hostname=hostname,
            manifest=build_orsha_manifest(
                hostname=hostname,
                offer_specs=(),
                enforce_offer_bounds=False,
            ),
        )

    @classmethod
    async def plan(
        cls,
        session: AsyncSession,
        *,
        action: str,
        hostname: str,
        offer_specs: Iterable[OrshaStorefrontOfferSpec | Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        return await StorefrontOnboardingService.plan(
            session,
            action=action,
            hostname=hostname,
            manifest=build_orsha_manifest(
                hostname=hostname,
                offer_specs=offer_specs,
                enforce_offer_bounds=action in {"bootstrap", "activate"},
            ),
        )

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
        return await StorefrontOnboardingService.execute(
            session,
            action=action,
            hostname=hostname,
            plan_token=plan_token,
            manifest=build_orsha_manifest(
                hostname=hostname,
                offer_specs=offer_specs,
                enforce_offer_bounds=action in {"bootstrap", "activate"},
            ),
        )


__all__ = [
    "ORSHA_ALLOWED_HOSTNAMES",
    "OrshaStorefrontBootstrapBlockedError",
    "OrshaStorefrontBootstrapService",
    "build_orsha_manifest",
]
