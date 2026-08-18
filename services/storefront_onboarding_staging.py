from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from models import Storefront, StorefrontDomain, Tenant, TenantAuditEvent
from models.tenancy import TenantScope
from services.storefront_onboarding_manifest import StorefrontOnboardingManifest
from services.storefront_onboarding_state import LoadedStorefrontOnboardingState
from services.tenant_offer_catalog_invalidation import (
    TenantOfferCatalogInvalidationAdapter,
)
from services.tenant_offer_mutation_staging_service import (
    TenantOfferMutationStagingService,
)


class StorefrontOnboardingStagingService:
    """Stage one reviewed lifecycle action without owning its transaction."""

    @classmethod
    async def stage(
        cls,
        session: AsyncSession,
        *,
        action: str,
        hostname: str,
        manifest: StorefrontOnboardingManifest,
        state: LoadedStorefrontOnboardingState,
        request_id: str,
    ) -> tuple[int, bool]:
        if action == "bootstrap":
            return await cls._stage_bootstrap(
                session,
                hostname=hostname,
                manifest=manifest,
                state=state,
                request_id=request_id,
            )
        if action == "verify-domain":
            return await cls._stage_verify_domain(
                session,
                manifest=manifest,
                state=state,
                request_id=request_id,
            )
        if action == "activate":
            return await cls._stage_activate(
                session,
                manifest=manifest,
                state=state,
                request_id=request_id,
            )
        return await cls._stage_disable(
            session,
            manifest=manifest,
            state=state,
            request_id=request_id,
        )

    @classmethod
    async def _stage_bootstrap(
        cls,
        session: AsyncSession,
        *,
        hostname: str,
        manifest: StorefrontOnboardingManifest,
        state: LoadedStorefrontOnboardingState,
        request_id: str,
    ) -> tuple[int, bool]:
        tenant = state.tenant
        tenant_created = tenant is None
        tenant_changes: dict[str, dict[str, Any]] = {}
        if tenant is None:
            tenant = Tenant(
                slug=manifest.tenant.slug,
                display_name=manifest.tenant.display_name,
                kind=manifest.tenant.kind,
                status="active",
                is_system=False,
            )
            session.add(tenant)
            await session.flush()
            tenant_changes = cls._creation_change_set(
                {
                    "slug": manifest.tenant.slug,
                    "display_name": manifest.tenant.display_name,
                    "kind": manifest.tenant.kind,
                    "status": "active",
                    "is_system": False,
                }
            )
        elif manifest.tenant.lifecycle == "managed":
            tenant_changes = cls._apply_model_changes(tenant, {"status": "active"})
        assert tenant.id is not None

        changed = 0
        storefront = state.storefront
        storefront_created = storefront is None
        if storefront is None:
            storefront = Storefront(
                tenant_id=int(tenant.id),
                **manifest.storefront.target(),
            )
            session.add(storefront)
            await session.flush()
            storefront_changes = cls._creation_change_set(
                manifest.storefront.target()
            )
        else:
            storefront_changes = cls._apply_model_changes(
                storefront, {"status": "draft"}
            )
        assert storefront.id is not None

        if tenant_changes:
            cls._add_audit(
                session,
                manifest=manifest,
                tenant_id=int(tenant.id),
                storefront_id=int(storefront.id),
                entity_type="tenant",
                entity_id=int(tenant.id),
                action=(
                    "tenant.onboarding_created"
                    if tenant_created
                    else "tenant.onboarding_enabled"
                ),
                change_set=tenant_changes,
                request_id=request_id,
            )
            changed += 1
        if storefront_changes:
            cls._add_audit(
                session,
                manifest=manifest,
                tenant_id=int(tenant.id),
                storefront_id=int(storefront.id),
                entity_type="storefront",
                entity_id=int(storefront.id),
                action=(
                    "storefront.onboarding_created"
                    if storefront_created
                    else "storefront.onboarding_prepared"
                ),
                change_set=storefront_changes,
                request_id=request_id,
            )
            changed += 1

        domain = state.domains[0] if state.domains else None
        if domain is None:
            domain = StorefrontDomain(
                storefront_id=int(storefront.id),
                hostname=hostname,
                status="pending",
                is_primary=True,
            )
            session.add(domain)
            await session.flush()
            domain_changes = cls._creation_change_set(
                {"hostname": hostname, "status": "pending", "is_primary": True}
            )
            domain_action = "storefront_domain.onboarding_created"
        else:
            domain_target: dict[str, Any] = {"status": "pending"}
            if domain.status == "disabled":
                domain_target["verified_at"] = None
            domain_changes = cls._apply_model_changes(domain, domain_target)
            domain_action = "storefront_domain.onboarding_prepared"
        if domain_changes:
            cls._add_audit(
                session,
                manifest=manifest,
                tenant_id=int(tenant.id),
                storefront_id=int(storefront.id),
                entity_type="storefront_domain",
                entity_id=int(domain.id),
                action=domain_action,
                change_set=domain_changes,
                request_id=request_id,
            )
            changed += 1

        tenant_scope = cls._tenant_scope(
            manifest=manifest,
            tenant_id=int(tenant.id),
            storefront_id=int(storefront.id),
        )
        for item in state.resolved_offers:
            mutation = await TenantOfferMutationStagingService.stage_upsert(
                session,
                payload={
                    "product_id": int(item.product.id),
                    "price": item.spec.price,
                    "old_price": item.spec.old_price,
                    "is_published": item.spec.is_published,
                    "status": "active",
                },
                tenant_scope=tenant_scope,
                actor_username=manifest.actor_username,
                actor_staff_user_id=None,
                request_id=request_id,
                stage_catalog_invalidation=False,
            )
            changed += int(mutation.changed)
        return changed, False

    @classmethod
    async def _stage_verify_domain(
        cls,
        session: AsyncSession,
        *,
        manifest: StorefrontOnboardingManifest,
        state: LoadedStorefrontOnboardingState,
        request_id: str,
    ) -> tuple[int, bool]:
        tenant = state.tenant
        storefront = state.storefront
        domain = state.domains[0]
        assert tenant is not None and tenant.id is not None
        assert storefront is not None and storefront.id is not None
        if domain.verified_at is not None:
            return 0, False
        changes = cls._apply_model_changes(
            domain,
            {"verified_at": datetime.now(timezone.utc)},
        )
        cls._add_audit(
            session,
            manifest=manifest,
            tenant_id=int(tenant.id),
            storefront_id=int(storefront.id),
            entity_type="storefront_domain",
            entity_id=int(domain.id),
            action="storefront_domain.onboarding_verified",
            change_set=changes,
            request_id=request_id,
        )
        return 1, False

    @classmethod
    async def _stage_activate(
        cls,
        session: AsyncSession,
        *,
        manifest: StorefrontOnboardingManifest,
        state: LoadedStorefrontOnboardingState,
        request_id: str,
    ) -> tuple[int, bool]:
        tenant = state.tenant
        storefront = state.storefront
        domain = state.domains[0]
        assert tenant is not None and tenant.id is not None
        assert storefront is not None and storefront.id is not None
        storefront_changes = cls._apply_model_changes(
            storefront, {"status": "active"}
        )
        domain_changes = cls._apply_model_changes(domain, {"status": "active"})
        changed = 0
        for entity, entity_type, action, change_set in (
            (
                storefront,
                "storefront",
                "storefront.onboarding_activated",
                storefront_changes,
            ),
            (
                domain,
                "storefront_domain",
                "storefront_domain.onboarding_activated",
                domain_changes,
            ),
        ):
            if not change_set:
                continue
            cls._add_audit(
                session,
                manifest=manifest,
                tenant_id=int(tenant.id),
                storefront_id=int(storefront.id),
                entity_type=entity_type,
                entity_id=int(entity.id),
                action=action,
                change_set=change_set,
                request_id=request_id,
            )
            changed += 1
        await session.flush()
        invalidation_staged = False
        if changed:
            invalidation_staged = await cls._stage_catalog_invalidation(
                session,
                manifest=manifest,
                state=state,
                reason="storefront_onboarding_activated",
            )
        return changed, invalidation_staged

    @classmethod
    async def _stage_disable(
        cls,
        session: AsyncSession,
        *,
        manifest: StorefrontOnboardingManifest,
        state: LoadedStorefrontOnboardingState,
        request_id: str,
    ) -> tuple[int, bool]:
        tenant = state.tenant
        storefront = state.storefront
        if (
            tenant is None
            or tenant.id is None
            or storefront is None
            or storefront.id is None
        ):
            return 0, False
        domain = next(iter(state.domains), None)
        routable = (
            tenant.status == "active"
            and storefront.status == "active"
            and domain is not None
            and domain.status == "active"
        )
        needs_change = (
            (
                manifest.tenant.lifecycle == "managed"
                and tenant.status != "disabled"
            )
            or storefront.status != "disabled"
            or (domain is not None and domain.status != "disabled")
            or any(
                offer.status != "disabled" or offer.is_published
                for offer, _ in state.offers
            )
        )
        invalidation_staged = False
        if routable and needs_change:
            invalidation_staged = await cls._stage_catalog_invalidation(
                session,
                manifest=manifest,
                state=state,
                reason="storefront_onboarding_disabled",
            )

        tenant_scope = cls._tenant_scope(
            manifest=manifest,
            tenant_id=int(tenant.id),
            storefront_id=int(storefront.id),
        )
        changed = 0
        for offer, _ in state.offers:
            mutation = await TenantOfferMutationStagingService.stage_update(
                session,
                offer_id=int(offer.id),
                payload={"status": "disabled", "is_published": False},
                tenant_scope=tenant_scope,
                actor_username=manifest.actor_username,
                actor_staff_user_id=None,
                request_id=request_id,
                stage_catalog_invalidation=False,
            )
            changed += int(mutation.changed)

        for entity, entity_type, action, target in (
            (
                domain,
                "storefront_domain",
                "storefront_domain.onboarding_disabled",
                {"status": "disabled"},
            ),
            (
                storefront,
                "storefront",
                "storefront.onboarding_disabled",
                {"status": "disabled"},
            ),
            (
                tenant if manifest.tenant.lifecycle == "managed" else None,
                "tenant",
                "tenant.onboarding_disabled",
                {"status": "disabled"},
            ),
        ):
            if entity is None:
                continue
            change_set = cls._apply_model_changes(entity, target)
            if not change_set:
                continue
            cls._add_audit(
                session,
                manifest=manifest,
                tenant_id=int(tenant.id),
                storefront_id=int(storefront.id),
                entity_type=entity_type,
                entity_id=int(entity.id),
                action=action,
                change_set=change_set,
                request_id=request_id,
            )
            changed += 1
        return changed, invalidation_staged

    @classmethod
    async def _stage_catalog_invalidation(
        cls,
        session: AsyncSession,
        *,
        manifest: StorefrontOnboardingManifest,
        state: LoadedStorefrontOnboardingState,
        reason: str,
    ) -> bool:
        tenant = state.tenant
        storefront = state.storefront
        assert tenant is not None and tenant.id is not None
        assert storefront is not None and storefront.id is not None
        return await TenantOfferCatalogInvalidationAdapter.stage(
            session,
            reason=reason,
            tenant_scope=cls._tenant_scope(
                manifest=manifest,
                tenant_id=int(tenant.id),
                storefront_id=int(storefront.id),
            ),
            product_ids=[int(product.id) for _, product in state.offers],
            slugs=[product.slug for _, product in state.offers],
            required=True,
        )

    @staticmethod
    def _tenant_scope(
        *,
        manifest: StorefrontOnboardingManifest,
        tenant_id: int,
        storefront_id: int,
    ) -> TenantScope:
        return TenantScope(
            tenant_id=tenant_id,
            storefront_id=storefront_id,
            is_system=manifest.tenant.is_system,
            is_canonical_storefront=(
                manifest.tenant.is_system and manifest.storefront.is_default
            ),
        )

    @classmethod
    def _apply_model_changes(
        cls,
        instance: Any,
        target: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        changes: dict[str, dict[str, Any]] = {}
        for field, value in target.items():
            before = getattr(instance, field)
            if before == value:
                continue
            changes[field] = {
                "before": cls._audit_value(before),
                "after": cls._audit_value(value),
            }
            setattr(instance, field, value)
        if changes and hasattr(instance, "updated_at"):
            instance.updated_at = datetime.now(timezone.utc)
        return changes

    @classmethod
    def _creation_change_set(
        cls,
        values: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        return {
            field: {"before": None, "after": cls._audit_value(value)}
            for field, value in values.items()
        }

    @staticmethod
    def _audit_value(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    @staticmethod
    def _add_audit(
        session: AsyncSession,
        *,
        manifest: StorefrontOnboardingManifest,
        tenant_id: int,
        storefront_id: int,
        entity_type: str,
        entity_id: int,
        action: str,
        change_set: dict[str, Any],
        request_id: str,
    ) -> None:
        session.add(
            TenantAuditEvent(
                tenant_id=tenant_id,
                storefront_id=storefront_id,
                actor_staff_user_id=None,
                actor_username=manifest.actor_username,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                request_id=request_id,
                change_set=change_set,
            )
        )


__all__ = ["StorefrontOnboardingStagingService"]
