from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from crud.storefront_onboarding import StorefrontOnboardingDAO
from services.storefront_onboarding_manifest import (
    MAX_ALLOWED_HOSTNAMES,
    MAX_OFFERS,
    StorefrontOnboardingManifest,
)
from services.storefront_onboarding_state import (
    LoadedStorefrontOnboardingState,
    ResolvedStorefrontOnboardingOffer,
    datetime_value,
    serialize_state,
    token_state,
)
from services.tenant_offer_catalog_invalidation import (
    TenantOfferCatalogInvalidationAdapter,
)


class StorefrontOnboardingPlanner:
    ACTIONS = frozenset({"bootstrap", "verify-domain", "activate", "disable"})

    @classmethod
    async def build(
        cls,
        session: AsyncSession,
        *,
        action: str,
        hostname: str,
        manifest: StorefrontOnboardingManifest,
        for_update: bool,
    ) -> tuple[dict[str, Any], LoadedStorefrontOnboardingState]:
        normalized_action = cls.normalize_action(action)
        normalized_hostname = manifest.normalize_selected_hostname(hostname)
        resolve_manifest_offers = normalized_action in {"bootstrap", "activate"}
        state = await cls.load_state(
            session,
            hostname=normalized_hostname,
            manifest=manifest,
            resolve_manifest_offers=resolve_manifest_offers,
            for_update=for_update,
        )
        blockers = cls.base_blockers(
            state,
            manifest=manifest,
            hostname=normalized_hostname,
        )
        blockers.extend(state.resolution_blockers)
        if normalized_action == "bootstrap":
            action_blockers, changes = cls._plan_bootstrap(
                state, manifest=manifest, hostname=normalized_hostname
            )
        elif normalized_action == "verify-domain":
            action_blockers, changes = cls._plan_verify_domain(state)
        elif normalized_action == "activate":
            action_blockers, changes = cls._plan_activate(
                state, manifest=manifest
            )
        else:
            action_blockers, changes = cls._plan_disable(
                state, manifest=manifest
            )
        blockers.extend(action_blockers)
        blockers = list(dict.fromkeys(blockers))
        serialized_state = serialize_state(state)
        resolved_offers = [offer.to_dict() for offer in state.resolved_offers]
        plan_digest = cls._plan_digest(
            action=normalized_action,
            hostname=normalized_hostname,
            manifest_fingerprint=manifest.fingerprint,
            state=token_state(serialized_state),
            resolved_offers=resolved_offers,
            blockers=blockers,
            changes=changes,
        )
        return (
            {
                "mode": "plan",
                "action": normalized_action,
                "tenant_slug": manifest.tenant.slug,
                "storefront_slug": manifest.storefront.slug,
                "hostname": normalized_hostname,
                "manifest_fingerprint": manifest.fingerprint,
                "manifest_summary": {
                    "version": manifest.version,
                    "tenant_lifecycle": manifest.tenant.lifecycle,
                    "tenant_kind": manifest.tenant.kind,
                    "tenant_is_system": manifest.tenant.is_system,
                    "allowed_hostnames": list(manifest.allowed_hostnames),
                    "offer_count": len(manifest.offers),
                },
                "ready": not blockers,
                "blockers": blockers,
                "changes": changes,
                "resolved_offers": resolved_offers,
                "plan_digest": plan_digest,
                "state": serialized_state,
            },
            state,
        )

    @classmethod
    async def load_state(
        cls,
        session: AsyncSession,
        *,
        hostname: str,
        manifest: StorefrontOnboardingManifest,
        resolve_manifest_offers: bool,
        for_update: bool,
    ) -> LoadedStorefrontOnboardingState:
        tenant = await StorefrontOnboardingDAO.get_tenant(
            session,
            slug=manifest.tenant.slug,
            for_update=for_update,
        )
        tenant_storefronts = []
        storefront = None
        if tenant is not None and tenant.id is not None:
            tenant_storefronts = (
                await StorefrontOnboardingDAO.list_tenant_storefronts(
                    session,
                    tenant_id=int(tenant.id),
                    for_update=for_update,
                    limit=MAX_OFFERS + 1,
                )
            )
            storefront = next(
                (
                    candidate
                    for candidate in tenant_storefronts
                    if candidate.slug == manifest.storefront.slug
                ),
                None,
            )

        domain_lock_set = await StorefrontOnboardingDAO.list_domain_lock_set(
            session,
            storefront_id=(
                int(storefront.id)
                if storefront is not None and storefront.id is not None
                else None
            ),
            hostname=hostname,
            for_update=for_update,
            limit=MAX_ALLOWED_HOSTNAMES + 2,
        )
        domains = [
            domain
            for domain in domain_lock_set
            if storefront is not None and domain.storefront_id == storefront.id
        ]
        hostname_owner = next(
            (domain for domain in domain_lock_set if domain.hostname == hostname),
            None,
        )

        offer_specs = manifest.offers if resolve_manifest_offers else ()
        resolved_offers, resolution_blockers = await cls._resolve_offers(
            session,
            offer_specs=offer_specs,
            for_update=for_update,
        )
        offers = []
        crm_counts = {"customers_in_tenant": 0, "leads": 0, "orders": 0}
        if tenant is not None and tenant.id is not None:
            if storefront is not None and storefront.id is not None:
                offers = await StorefrontOnboardingDAO.list_offers_with_products(
                    session,
                    tenant_id=int(tenant.id),
                    storefront_id=int(storefront.id),
                    for_update=for_update,
                    limit=MAX_OFFERS + 1,
                )
            crm_counts = await StorefrontOnboardingDAO.crm_counts(
                session,
                tenant_id=int(tenant.id),
                storefront_id=(
                    int(storefront.id)
                    if storefront is not None and storefront.id is not None
                    else None
                ),
            )
        return LoadedStorefrontOnboardingState(
            tenant=tenant,
            storefront=storefront,
            tenant_storefronts=tenant_storefronts,
            domains=domains,
            hostname_owner=hostname_owner,
            offers=offers,
            resolved_offers=resolved_offers,
            resolution_blockers=resolution_blockers,
            crm_counts=crm_counts,
        )

    @classmethod
    async def _resolve_offers(
        cls,
        session: AsyncSession,
        *,
        offer_specs,
        for_update: bool,
    ) -> tuple[list[ResolvedStorefrontOnboardingOffer], list[str]]:
        products = await StorefrontOnboardingDAO.resolve_products(
            session,
            product_ids=[
                spec.product_id for spec in offer_specs if spec.product_id is not None
            ],
            product_slugs=[
                spec.product_slug
                for spec in offer_specs
                if spec.product_slug is not None
            ],
            for_update=for_update,
        )
        by_id = {int(product.id): product for product in products}
        by_slug = {product.slug: product for product in products}
        resolved: list[ResolvedStorefrontOnboardingOffer] = []
        blockers: list[str] = []
        seen_product_ids: set[int] = set()
        for spec in offer_specs:
            product = (
                by_id.get(spec.product_id)
                if spec.product_id is not None
                else by_slug.get(str(spec.product_slug))
            )
            if product is None or product.id is None:
                blockers.append(f"product {spec.reference} was not found")
                continue
            product_id = int(product.id)
            if product_id in seen_product_ids:
                blockers.append(f"product {product_id} is referenced more than once")
                continue
            seen_product_ids.add(product_id)
            if not product.is_published:
                blockers.append(f"product {product_id} is not globally published")
            resolved.append(
                ResolvedStorefrontOnboardingOffer(spec=spec, product=product)
            )
        resolved.sort(key=lambda item: int(item.product.id))
        return resolved, blockers

    @classmethod
    def base_blockers(
        cls,
        state: LoadedStorefrontOnboardingState,
        *,
        manifest: StorefrontOnboardingManifest,
        hostname: str,
    ) -> list[str]:
        blockers: list[str] = []
        tenant = state.tenant
        storefront = state.storefront
        owner = state.hostname_owner
        if owner is not None and (
            storefront is None or owner.storefront_id != storefront.id
        ):
            blockers.append("requested hostname is owned by another storefront")
        if tenant is None:
            if manifest.tenant.lifecycle == "existing":
                blockers.append("manifest requires an existing tenant")
            return blockers

        expected_tenant = {
            "slug": manifest.tenant.slug,
            "display_name": manifest.tenant.display_name,
            "kind": manifest.tenant.kind,
            "is_system": manifest.tenant.is_system,
        }
        for field, value in expected_tenant.items():
            if getattr(tenant, field) != value:
                blockers.append(f"tenant {field} has unexpected ownership data")
        if manifest.tenant.lifecycle == "existing" and tenant.status != "active":
            blockers.append("existing tenant is not active")
        if manifest.tenant.lifecycle == "managed":
            if len(state.tenant_storefronts) > 1:
                blockers.append("managed tenant has storefronts outside this manifest")
            elif state.tenant_storefronts and storefront is None:
                blockers.append("managed tenant has a different storefront")
        if storefront is None:
            return blockers

        expected_storefront = {
            "tenant_id": int(tenant.id),
            "slug": manifest.storefront.slug,
            "display_name": manifest.storefront.display_name,
            "city": manifest.storefront.city,
            "default_locale": manifest.storefront.default_locale,
            "currency": manifest.storefront.currency,
            "is_default": manifest.storefront.is_default,
        }
        for field, value in expected_storefront.items():
            if getattr(storefront, field) != value:
                blockers.append(f"storefront {field} has unexpected ownership data")
        if len(state.domains) > 1:
            blockers.append("storefront has more than one managed domain")
        if state.domains:
            domain = state.domains[0]
            if domain.hostname != hostname:
                blockers.append(
                    "storefront hostname differs from the reviewed hostname"
                )
            if not domain.is_primary:
                blockers.append("storefront domain is not primary")
        if len(cls._manifest_owned_offers(state)) > MAX_OFFERS:
            blockers.append(f"storefront has more than {MAX_OFFERS} offers")
        return blockers

    @classmethod
    def _plan_bootstrap(
        cls,
        state: LoadedStorefrontOnboardingState,
        *,
        manifest: StorefrontOnboardingManifest,
        hostname: str,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        blockers: list[str] = []
        changes: list[dict[str, Any]] = []
        tenant = state.tenant
        storefront = state.storefront
        if tenant is None:
            if manifest.tenant.lifecycle == "managed":
                changes.append(
                    cls._create_change(
                        "tenant",
                        {
                            "slug": manifest.tenant.slug,
                            "display_name": manifest.tenant.display_name,
                            "kind": manifest.tenant.kind,
                            "status": "active",
                            "is_system": False,
                        },
                    )
                )
        elif manifest.tenant.lifecycle == "managed":
            cls._append_update(changes, "tenant", tenant, {"status": "active"})

        if storefront is not None and storefront.status == "active":
            blockers.append("active storefront must be disabled before bootstrap changes")
        if storefront is None:
            changes.append(
                cls._create_change("storefront", manifest.storefront.target())
            )
        else:
            cls._append_update(changes, "storefront", storefront, {"status": "draft"})

        if not state.domains:
            changes.append(
                cls._create_change(
                    "storefront_domain",
                    {"hostname": hostname, "status": "pending", "is_primary": True},
                )
            )
        elif len(state.domains) == 1:
            domain = state.domains[0]
            target: dict[str, Any] = {"status": "pending"}
            if domain.status == "disabled":
                target["verified_at"] = None
            cls._append_update(changes, "storefront_domain", domain, target)

        existing_by_product = {
            int(offer.product_id): offer
            for offer, _ in cls._manifest_owned_offers(state)
        }
        desired_ids = {int(item.product.id) for item in state.resolved_offers}
        extras = sorted(set(existing_by_product) - desired_ids)
        if extras:
            blockers.append(
                "storefront has offers outside the reviewed manifest: "
                + ",".join(str(value) for value in extras)
            )
        for item in state.resolved_offers:
            product_id = int(item.product.id)
            target = {
                "product_id": product_id,
                "price": item.spec.price,
                "old_price": item.spec.old_price,
                "is_published": item.spec.is_published,
                "status": "active",
            }
            existing = existing_by_product.get(product_id)
            if existing is None:
                changes.append(cls._create_change("tenant_offer", target))
            else:
                cls._append_update(changes, "tenant_offer", existing, target)
        return blockers, cls._sort_changes(changes)

    @classmethod
    def _plan_verify_domain(
        cls,
        state: LoadedStorefrontOnboardingState,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        blockers: list[str] = []
        storefront = state.storefront
        if state.tenant is None or storefront is None:
            return ["storefront is not bootstrapped"], []
        if state.tenant.status != "active":
            blockers.append("tenant must be active before domain verification")
        if storefront.status not in {"draft", "active"}:
            blockers.append("disabled storefront must be bootstrapped before verification")
        if len(state.domains) != 1:
            blockers.append("exactly one primary domain must be bootstrapped")
            return blockers, []
        domain = state.domains[0]
        if domain.status not in {"pending", "active"}:
            blockers.append("disabled domain must be bootstrapped before verification")
        changes: list[dict[str, Any]] = []
        if domain.verified_at is None:
            changes.append(
                {
                    "entity": "storefront_domain",
                    "entity_id": int(domain.id),
                    "operation": "update",
                    "fields": {
                        "verified_at": {
                            "before": None,
                            "after": "database-time-on-execute",
                        }
                    },
                }
            )
        return blockers, cls._sort_changes(changes)

    @classmethod
    def _plan_activate(
        cls,
        state: LoadedStorefrontOnboardingState,
        *,
        manifest: StorefrontOnboardingManifest,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        blockers: list[str] = []
        changes: list[dict[str, Any]] = []
        tenant = state.tenant
        storefront = state.storefront
        if tenant is None or storefront is None:
            return ["storefront is not bootstrapped"], changes
        if tenant.status != "active":
            blockers.append("tenant must be active before activation")
        if storefront.status == "disabled":
            blockers.append("disabled storefront must be bootstrapped before activation")
        elif storefront.status not in {"draft", "active"}:
            blockers.append("storefront lifecycle is unexpected")
        if len(state.domains) != 1:
            blockers.append("exactly one primary domain must be bootstrapped")
        else:
            domain = state.domains[0]
            if domain.status == "disabled":
                blockers.append("disabled domain must be bootstrapped before activation")
            elif domain.status not in {"pending", "active"}:
                blockers.append("domain lifecycle is unexpected")
            if domain.verified_at is None:
                blockers.append("domain must be verified before activation")

        existing_by_product = {
            int(offer.product_id): offer
            for offer, _ in cls._manifest_owned_offers(state)
        }
        desired_ids = {int(item.product.id) for item in state.resolved_offers}
        if set(existing_by_product) != desired_ids:
            blockers.append("stored offers differ from the reviewed manifest")
        for item in state.resolved_offers:
            offer = existing_by_product.get(int(item.product.id))
            target = {
                "price": item.spec.price,
                "old_price": item.spec.old_price,
                "is_published": item.spec.is_published,
                "status": "active",
            }
            if offer is None or any(
                getattr(offer, key) != value for key, value in target.items()
            ):
                blockers.append(
                    f"offer for product {int(item.product.id)} is not bootstrap-ready"
                )
        if manifest.offers and not any(
            item.spec.is_published for item in state.resolved_offers
        ):
            blockers.append("activation requires a published offer when offers exist")

        cls._append_update(changes, "storefront", storefront, {"status": "active"})
        if len(state.domains) == 1:
            cls._append_update(
                changes, "storefront_domain", state.domains[0], {"status": "active"}
            )
        if changes and not TenantOfferCatalogInvalidationAdapter.available():
            blockers.append("storefront catalog invalidation staging is unavailable")
        return blockers, cls._sort_changes(changes)

    @classmethod
    def _plan_disable(
        cls,
        state: LoadedStorefrontOnboardingState,
        *,
        manifest: StorefrontOnboardingManifest,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        changes: list[dict[str, Any]] = []
        tenant = state.tenant
        storefront = state.storefront
        if tenant is None or storefront is None:
            return [], changes
        if manifest.tenant.lifecycle == "managed":
            cls._append_update(changes, "tenant", tenant, {"status": "disabled"})
        cls._append_update(changes, "storefront", storefront, {"status": "disabled"})
        if len(state.domains) == 1:
            cls._append_update(
                changes,
                "storefront_domain",
                state.domains[0],
                {"status": "disabled"},
            )
        for offer, _ in cls._manifest_owned_offers(state):
            cls._append_update(
                changes,
                "tenant_offer",
                offer,
                {"status": "disabled", "is_published": False},
            )
        domain = state.domains[0] if len(state.domains) == 1 else None
        routable = (
            tenant.status == "active"
            and storefront.status == "active"
            and domain is not None
            and domain.status == "active"
        )
        if changes and routable and not TenantOfferCatalogInvalidationAdapter.available():
            return (
                ["storefront catalog invalidation staging is unavailable"],
                cls._sort_changes(changes),
            )
        return [], cls._sort_changes(changes)

    @classmethod
    def normalize_action(cls, action: str) -> str:
        normalized = str(action or "").strip().lower()
        if normalized not in cls.ACTIONS:
            raise ValueError(
                "action must be bootstrap, verify-domain, activate, or disable"
            )
        return normalized

    @staticmethod
    def _manifest_owned_offers(
        state: LoadedStorefrontOnboardingState,
    ) -> list[tuple[Any, Any]]:
        return [
            (offer, product)
            for offer, product in state.offers
            if offer.catalog_grant_id is None
        ]

    @staticmethod
    def _plan_digest(
        *,
        action: str,
        hostname: str,
        manifest_fingerprint: str,
        state: dict[str, Any],
        resolved_offers: list[dict[str, Any]],
        blockers: list[str],
        changes: list[dict[str, Any]],
    ) -> str:
        payload = {
            "version": 2,
            "action": action,
            "hostname": hostname,
            "manifest_fingerprint": manifest_fingerprint,
            "state": state,
            "resolved_offers": resolved_offers,
            "blockers": blockers,
            "changes": changes,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _create_change(entity: str, fields: dict[str, Any]) -> dict[str, Any]:
        return {"entity": entity, "operation": "create", "fields": fields}

    @classmethod
    def _append_update(
        cls,
        changes: list[dict[str, Any]],
        entity: str,
        instance: Any,
        target: dict[str, Any],
    ) -> None:
        fields = {
            field: {
                "before": cls._audit_value(getattr(instance, field)),
                "after": cls._audit_value(value),
            }
            for field, value in target.items()
            if getattr(instance, field) != value
        }
        if fields:
            changes.append(
                {
                    "entity": entity,
                    "entity_id": int(instance.id),
                    "operation": "update",
                    "fields": fields,
                }
            )

    @staticmethod
    def _sort_changes(changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            changes,
            key=lambda item: (
                str(item["entity"]),
                int(
                    item.get("entity_id")
                    or item.get("fields", {}).get("product_id")
                    or 0
                ),
                str(item["operation"]),
            ),
        )

    @staticmethod
    def _audit_value(value: Any) -> Any:
        return datetime_value(value) if hasattr(value, "isoformat") else value


__all__ = ["StorefrontOnboardingPlanner"]
