"""Deprecated Orsha names retained as aliases to generic onboarding state."""

from __future__ import annotations

from typing import Any

from services.storefront_onboarding_state import (
    LoadedStorefrontOnboardingState,
    ResolvedStorefrontOnboardingOffer,
    StorefrontOnboardingBlockedError,
    datetime_value,
    serialize_state,
    token_state,
)


OrshaStorefrontBootstrapBlockedError = StorefrontOnboardingBlockedError
LoadedOrshaStorefrontState = LoadedStorefrontOnboardingState
ResolvedOrshaOffer = ResolvedStorefrontOnboardingOffer


class OrshaStorefrontDefinition:
    TENANT_SLUG = "mvn"
    STOREFRONT_SLUG = "orsha"
    STOREFRONT_DISPLAY_NAME = "MVN Орша"
    STOREFRONT_CITY = "Орша"
    DEFAULT_LOCALE = "ru-BY"
    CURRENCY = "BYN"
    ACTOR_USERNAME = "system:storefront-onboarding:mvn:orsha"
    ACTIONS = frozenset({"bootstrap", "verify-domain", "activate", "disable"})

    @classmethod
    def storefront_target(cls) -> dict[str, Any]:
        return {
            "slug": cls.STOREFRONT_SLUG,
            "display_name": cls.STOREFRONT_DISPLAY_NAME,
            "status": "draft",
            "city": cls.STOREFRONT_CITY,
            "default_locale": cls.DEFAULT_LOCALE,
            "currency": cls.CURRENCY,
            "is_default": False,
        }


__all__ = [
    "LoadedOrshaStorefrontState",
    "OrshaStorefrontBootstrapBlockedError",
    "OrshaStorefrontDefinition",
    "ResolvedOrshaOffer",
    "datetime_value",
    "serialize_state",
    "token_state",
]
