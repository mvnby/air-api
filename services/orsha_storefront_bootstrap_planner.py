from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from crud.orsha_storefront_bootstrap import OrshaStorefrontBootstrapDAO
from services.orsha_storefront_bootstrap_state import (
    LoadedOrshaStorefrontState,
    OrshaStorefrontDefinition,
    ResolvedOrshaOffer,
    datetime_value,
    serialize_state,
    token_state,
)
from services.orsha_storefront_manifest import (
    OrshaStorefrontManifest,
    OrshaStorefrontManifestError,
    OrshaStorefrontOfferSpec,
)
from services.storefront_context_service import StorefrontContextService
from services.tenant_offer_catalog_invalidation import (
    TenantOfferCatalogInvalidationAdapter,
)


class OrshaStorefrontBootstrapPlanner:
    _HOST_PATTERN = re.compile(r"^orsha(?:-[a-z0-9]+(?:-[a-z0-9]+)*)?\.mvn\.by$")

    @classmethod
    async def build(
        cls,
        session: AsyncSession,
        *,
        action: str,
        hostname: str,
        offer_specs: Iterable[OrshaStorefrontOfferSpec | Mapping[str, Any]],
        for_update: bool,
    ) -> tuple[dict[str, Any], LoadedOrshaStorefrontState]:
        normalized_action = cls.normalize_action(action)
        normalized_hostname = cls.normalize_hostname(hostname)
        normalized_offers = cls.normalize_offer_specs(
            normalized_action,
            offer_specs,
        )
        state = await cls.load_state(
            session,
            hostname=normalized_hostname,
            offer_specs=normalized_offers,
            for_update=for_update,
        )
        blockers = cls.base_blockers(state, hostname=normalized_hostname)
        blockers.extend(state.resolution_blockers)
        if normalized_action == "bootstrap":
            action_blockers, changes = cls._plan_bootstrap(
                state,
                normalized_hostname,
            )
        elif normalized_action == "activate":
            action_blockers, changes = cls._plan_activate(state)
        else:
            action_blockers, changes = cls._plan_disable(state)
        blockers.extend(action_blockers)
        blockers = list(dict.fromkeys(blockers))
        serialized_state = serialize_state(state)
        resolved_offers = [offer.to_dict() for offer in state.resolved_offers]
        plan_token = cls._plan_token(
            action=normalized_action,
            hostname=normalized_hostname,
            state=token_state(serialized_state),
            resolved_offers=resolved_offers,
            blockers=blockers,
            changes=changes,
        )
        return (
            {
                "mode": "plan",
                "action": normalized_action,
                "tenant_slug": OrshaStorefrontDefinition.TENANT_SLUG,
                "storefront_slug": OrshaStorefrontDefinition.STOREFRONT_SLUG,
                "hostname": normalized_hostname,
                "ready": not blockers,
                "blockers": blockers,
                "changes": changes,
                "resolved_offers": resolved_offers,
                "plan_token": plan_token,
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
        offer_specs: tuple[OrshaStorefrontOfferSpec, ...],
        for_update: bool,
    ) -> LoadedOrshaStorefrontState:
        tenant = await OrshaStorefrontBootstrapDAO.get_tenant(
            session,
            slug=OrshaStorefrontDefinition.TENANT_SLUG,
            for_update=for_update,
        )
        storefront = None
        domains = []
        offers = []
        crm_counts = {"customers_in_tenant": 0, "leads": 0, "orders": 0}
        if tenant is not None and tenant.id is not None:
            storefront = await OrshaStorefrontBootstrapDAO.get_storefront(
                session,
                tenant_id=int(tenant.id),
                slug=OrshaStorefrontDefinition.STOREFRONT_SLUG,
                for_update=for_update,
            )
            if storefront is not None and storefront.id is not None:
                domains = await OrshaStorefrontBootstrapDAO.list_domains(
                    session,
                    storefront_id=int(storefront.id),
                    for_update=for_update,
                    limit=2,
                )
                offers = (
                    await OrshaStorefrontBootstrapDAO.list_offers_with_products(
                        session,
                        tenant_id=int(tenant.id),
                        storefront_id=int(storefront.id),
                        for_update=for_update,
                        limit=OrshaStorefrontManifest.MAX_OFFERS + 1,
                    )
                )
            crm_counts = await OrshaStorefrontBootstrapDAO.crm_counts(
                session,
                tenant_id=int(tenant.id),
                storefront_id=(
                    int(storefront.id)
                    if storefront is not None and storefront.id is not None
                    else None
                ),
            )
        hostname_owner = await OrshaStorefrontBootstrapDAO.get_domain_by_hostname(
            session,
            hostname=hostname,
            for_update=for_update,
        )
        resolved_offers, resolution_blockers = await cls._resolve_offers(
            session,
            offer_specs=offer_specs,
            for_update=for_update,
        )
        return LoadedOrshaStorefrontState(
            tenant=tenant,
            storefront=storefront,
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
        offer_specs: tuple[OrshaStorefrontOfferSpec, ...],
        for_update: bool,
    ) -> tuple[list[ResolvedOrshaOffer], list[str]]:
        products = await OrshaStorefrontBootstrapDAO.resolve_products(
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
        resolved: list[ResolvedOrshaOffer] = []
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
            resolved.append(ResolvedOrshaOffer(spec=spec, product=product))
        resolved.sort(key=lambda item: int(item.product.id))
        return resolved, blockers

    @classmethod
    def base_blockers(
        cls,
        state: LoadedOrshaStorefrontState,
        *,
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
            blockers.append("active system tenant mvn is unavailable")
            return blockers
        if (
            tenant.slug != OrshaStorefrontDefinition.TENANT_SLUG
            or not tenant.is_system
            or tenant.status != "active"
        ):
            blockers.append("tenant mvn ownership or lifecycle is unexpected")
        if storefront is None:
            return blockers

        expected = {
            "tenant_id": int(tenant.id),
            "slug": OrshaStorefrontDefinition.STOREFRONT_SLUG,
            "display_name": OrshaStorefrontDefinition.STOREFRONT_DISPLAY_NAME,
            "city": OrshaStorefrontDefinition.STOREFRONT_CITY,
            "default_locale": OrshaStorefrontDefinition.DEFAULT_LOCALE,
            "currency": OrshaStorefrontDefinition.CURRENCY,
            "is_default": False,
        }
        for field, value in expected.items():
            if getattr(storefront, field) != value:
                blockers.append(f"storefront {field} has unexpected ownership data")
        if len(state.domains) > 1:
            blockers.append("Orsha storefront has more than one domain")
        if state.domains:
            domain = state.domains[0]
            if domain.hostname != hostname:
                blockers.append(
                    "Orsha storefront hostname differs from the reviewed hostname"
                )
            if not domain.is_primary:
                blockers.append("Orsha storefront domain is not primary")
        if len(state.offers) > OrshaStorefrontManifest.MAX_OFFERS:
            blockers.append("Orsha storefront has more than 20 offers")
        return blockers

    @classmethod
    def _plan_bootstrap(
        cls,
        state: LoadedOrshaStorefrontState,
        hostname: str,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        blockers: list[str] = []
        changes: list[dict[str, Any]] = []
        if state.storefront is not None and state.storefront.status == "active":
            blockers.append(
                "active Orsha storefront must be disabled before bootstrap changes"
            )
        if state.storefront is None:
            changes.append(
                cls._create_change(
                    "storefront",
                    OrshaStorefrontDefinition.storefront_target(),
                )
            )
        else:
            cls._append_update(
                changes,
                "storefront",
                state.storefront,
                {"status": "draft"},
            )
        if not state.domains:
            changes.append(
                cls._create_change(
                    "storefront_domain",
                    {"hostname": hostname, "status": "pending", "is_primary": True},
                )
            )
        elif len(state.domains) == 1:
            cls._append_update(
                changes,
                "storefront_domain",
                state.domains[0],
                {"status": "pending"},
            )

        existing_by_product = {
            int(offer.product_id): offer for offer, _ in state.offers
        }
        desired_ids = {int(item.product.id) for item in state.resolved_offers}
        extras = sorted(set(existing_by_product) - desired_ids)
        if extras:
            blockers.append(
                "Orsha has offers outside the reviewed allowlist: "
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
    def _plan_activate(
        cls,
        state: LoadedOrshaStorefrontState,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        blockers: list[str] = []
        changes: list[dict[str, Any]] = []
        storefront = state.storefront
        if storefront is None:
            return ["Orsha storefront is not bootstrapped"], changes
        if not state.domains:
            blockers.append("Orsha primary domain is not bootstrapped")
        if storefront.status == "disabled":
            blockers.append(
                "disabled Orsha storefront must be bootstrapped before activation"
            )
        elif storefront.status not in {"draft", "active"}:
            blockers.append("Orsha storefront lifecycle is unexpected")
        if state.domains:
            domain = state.domains[0]
            if domain.status == "disabled":
                blockers.append(
                    "disabled Orsha domain must be bootstrapped before activation"
                )
            elif domain.status not in {"pending", "active"}:
                blockers.append("Orsha domain lifecycle is unexpected")
            elif domain.status == "active" and domain.verified_at is None:
                blockers.append("active Orsha domain has no verification timestamp")

        existing_by_product = {
            int(offer.product_id): offer for offer, _ in state.offers
        }
        desired_ids = {int(item.product.id) for item in state.resolved_offers}
        if set(existing_by_product) != desired_ids:
            blockers.append("stored offers differ from the reviewed activation allowlist")
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
        if state.resolved_offers and not any(
            item.spec.is_published for item in state.resolved_offers
        ):
            blockers.append("activation requires at least one published offer")

        cls._append_update(changes, "storefront", storefront, {"status": "active"})
        if len(state.domains) == 1:
            cls._append_update(
                changes,
                "storefront_domain",
                state.domains[0],
                {"status": "active"},
            )
        if changes and not TenantOfferCatalogInvalidationAdapter.available():
            blockers.append("storefront catalog invalidation staging is unavailable")
        return blockers, cls._sort_changes(changes)

    @classmethod
    def _plan_disable(
        cls,
        state: LoadedOrshaStorefrontState,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        changes: list[dict[str, Any]] = []
        if state.storefront is None:
            return [], changes
        cls._append_update(
            changes,
            "storefront",
            state.storefront,
            {"status": "disabled"},
        )
        if len(state.domains) == 1:
            cls._append_update(
                changes,
                "storefront_domain",
                state.domains[0],
                {"status": "disabled"},
            )
        for offer, _ in state.offers:
            cls._append_update(
                changes,
                "tenant_offer",
                offer,
                {"status": "disabled", "is_published": False},
            )
        domain = state.domains[0] if len(state.domains) == 1 else None
        routable = (
            state.storefront.status == "active"
            and domain is not None
            and domain.status == "active"
        )
        if (
            changes
            and routable
            and not TenantOfferCatalogInvalidationAdapter.available()
        ):
            return (
                ["storefront catalog invalidation staging is unavailable"],
                cls._sort_changes(changes),
            )
        return [], cls._sort_changes(changes)

    @staticmethod
    def normalize_action(action: str) -> str:
        normalized = str(action or "").strip().lower()
        if normalized not in OrshaStorefrontDefinition.ACTIONS:
            raise ValueError("action must be bootstrap, activate, or disable")
        return normalized

    @classmethod
    def normalize_offer_specs(
        cls,
        action: str,
        offer_specs: Iterable[OrshaStorefrontOfferSpec | Mapping[str, Any]],
    ) -> tuple[OrshaStorefrontOfferSpec, ...]:
        values = [
            value.to_dict() if isinstance(value, OrshaStorefrontOfferSpec) else value
            for value in offer_specs
        ]
        if action == "disable":
            if values:
                raise OrshaStorefrontManifestError(
                    "disable does not accept an offer allowlist"
                )
            return ()
        return OrshaStorefrontManifest.normalize(values)

    @classmethod
    def normalize_hostname(cls, hostname: str) -> str:
        raw = str(hostname or "").strip()
        if ":" in raw:
            raise ValueError("Orsha hostname must not include a port")
        normalized = StorefrontContextService.normalize_hostname(raw)
        if not cls._HOST_PATTERN.fullmatch(normalized):
            raise ValueError("Orsha hostname must be orsha*.mvn.by")
        return normalized

    @classmethod
    def _plan_token(
        cls,
        *,
        action: str,
        hostname: str,
        state: dict[str, Any],
        resolved_offers: list[dict[str, Any]],
        blockers: list[str],
        changes: list[dict[str, Any]],
    ) -> str:
        payload = {
            "version": 1,
            "action": action,
            "tenant_slug": OrshaStorefrontDefinition.TENANT_SLUG,
            "storefront_slug": OrshaStorefrontDefinition.STOREFRONT_SLUG,
            "hostname": hostname,
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
