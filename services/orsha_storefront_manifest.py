"""Deprecated Orsha offer compatibility built on the generic manifest parser."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from services.storefront_onboarding_manifest import (
    StorefrontOnboardingManifest,
    StorefrontOnboardingManifestError,
    StorefrontOnboardingOfferSpec,
)


OrshaStorefrontManifestError = StorefrontOnboardingManifestError
OrshaStorefrontOfferSpec = StorefrontOnboardingOfferSpec


class OrshaStorefrontManifest:
    MIN_OFFERS = 5
    MAX_OFFERS = 20

    @classmethod
    def normalize(
        cls,
        values: Iterable[Mapping[str, Any]],
    ) -> tuple[StorefrontOnboardingOfferSpec, ...]:
        offers = list(values)
        if not cls.MIN_OFFERS <= len(offers) <= cls.MAX_OFFERS:
            raise StorefrontOnboardingManifestError(
                f"Orsha allowlist must contain between {cls.MIN_OFFERS} and "
                f"{cls.MAX_OFFERS} offers"
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
                "allowed_hostnames": ["orsha-internal.mvn.by"],
                "offers": offers,
            }
        ).offers


__all__ = [
    "OrshaStorefrontManifest",
    "OrshaStorefrontManifestError",
    "OrshaStorefrontOfferSpec",
]
