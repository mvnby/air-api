from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from models import Product, Storefront, StorefrontDomain, Tenant, TenantOffer
from services.storefront_onboarding_manifest import StorefrontOnboardingOfferSpec


class StorefrontOnboardingBlockedError(RuntimeError):
    """Raised when an onboarding plan is stale, unsafe, or already executing."""


@dataclass(frozen=True)
class ResolvedStorefrontOnboardingOffer:
    spec: StorefrontOnboardingOfferSpec
    product: Product

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference": self.spec.reference,
            "product_id": int(self.product.id),
            "product_slug": self.product.slug,
            "product_is_published": bool(self.product.is_published),
            "price": self.spec.price,
            "old_price": self.spec.old_price,
            "is_published": self.spec.is_published,
            "status": "active",
        }


@dataclass
class LoadedStorefrontOnboardingState:
    tenant: Tenant | None
    storefront: Storefront | None
    domains: list[StorefrontDomain]
    hostname_owner: StorefrontDomain | None
    offers: list[tuple[TenantOffer, Product]]
    resolved_offers: list[ResolvedStorefrontOnboardingOffer]
    resolution_blockers: list[str]
    crm_counts: dict[str, int]
    tenant_storefronts: list[Storefront] = field(default_factory=list)


def datetime_value(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def serialize_state(state: LoadedStorefrontOnboardingState) -> dict[str, Any]:
    tenant = state.tenant
    storefront = state.storefront
    return {
        "tenant": (
            None
            if tenant is None
            else {
                "id": int(tenant.id),
                "slug": tenant.slug,
                "display_name": tenant.display_name,
                "kind": tenant.kind,
                "status": tenant.status,
                "is_system": tenant.is_system,
                "updated_at": datetime_value(tenant.updated_at),
            }
        ),
        "storefront": serialize_storefront(storefront),
        "tenant_storefronts": [
            serialize_storefront(value) for value in state.tenant_storefronts
        ],
        "domains": [serialize_domain(domain) for domain in state.domains],
        "hostname_owner": serialize_domain(state.hostname_owner),
        "offers": [
            {
                "id": int(offer.id),
                "tenant_id": offer.tenant_id,
                "storefront_id": offer.storefront_id,
                "product_id": offer.product_id,
                "product_slug": product.slug,
                "product_is_published": bool(product.is_published),
                "price": offer.price,
                "old_price": offer.old_price,
                "is_published": offer.is_published,
                "status": offer.status,
                "updated_at": datetime_value(offer.updated_at),
            }
            for offer, product in state.offers
        ],
        "crm_counts": dict(state.crm_counts),
    }


def serialize_storefront(storefront: Storefront | None) -> dict[str, Any] | None:
    if storefront is None:
        return None
    return {
        "id": int(storefront.id),
        "tenant_id": storefront.tenant_id,
        "slug": storefront.slug,
        "display_name": storefront.display_name,
        "status": storefront.status,
        "city": storefront.city,
        "default_locale": storefront.default_locale,
        "currency": storefront.currency,
        "is_default": storefront.is_default,
        "updated_at": datetime_value(storefront.updated_at),
    }


def serialize_domain(domain: StorefrontDomain | None) -> dict[str, Any] | None:
    if domain is None:
        return None
    return {
        "id": int(domain.id),
        "storefront_id": domain.storefront_id,
        "hostname": domain.hostname,
        "status": domain.status,
        "is_primary": domain.is_primary,
        "verified_at": datetime_value(domain.verified_at),
        "updated_at": datetime_value(domain.updated_at),
    }


def token_state(state: dict[str, Any]) -> dict[str, Any]:
    # New CRM traffic must not invalidate a reviewed emergency-disable token.
    return {key: value for key, value in state.items() if key != "crm_counts"}


__all__ = [
    "LoadedStorefrontOnboardingState",
    "ResolvedStorefrontOnboardingOffer",
    "StorefrontOnboardingBlockedError",
    "datetime_value",
    "serialize_state",
    "token_state",
]
