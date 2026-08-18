"""Deprecated Orsha name for the generic transaction staging service."""

from services.storefront_onboarding_staging import (
    StorefrontOnboardingStagingService,
)


OrshaStorefrontLifecycleStagingService = StorefrontOnboardingStagingService


__all__ = ["OrshaStorefrontLifecycleStagingService"]
