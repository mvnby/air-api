from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from models import Storefront, StorefrontDomain, TenantAuditEvent
from models.tenancy import TenantScope
from services.orsha_storefront_bootstrap_state import (
    LoadedOrshaStorefrontState,
    OrshaStorefrontDefinition,
)
from services.tenant_offer_catalog_invalidation import (
    TenantOfferCatalogInvalidationAdapter,
)
from services.tenant_offer_mutation_staging_service import (
    TenantOfferMutationStagingService,
)


class OrshaStorefrontLifecycleStagingService:
    """Stage one reviewed lifecycle action without committing or rolling back."""

    @classmethod
    async def stage(
        cls,
        session: AsyncSession,
        *,
        action: str,
        hostname: str,
        state: LoadedOrshaStorefrontState,
        request_id: str,
    ) -> tuple[int, bool]:
        if action == "bootstrap":
            return await cls._stage_bootstrap(
                session,
                hostname=hostname,
                state=state,
                request_id=request_id,
            )
        if action == "activate":
            return await cls._stage_activate(
                session,
                state=state,
                request_id=request_id,
            )
        return await cls._stage_disable(
            session,
            state=state,
            request_id=request_id,
        )

    @classmethod
    async def _stage_bootstrap(
        cls,
        session: AsyncSession,
        *,
        hostname: str,
        state: LoadedOrshaStorefrontState,
        request_id: str,
    ) -> tuple[int, bool]:
        tenant = state.tenant
        assert tenant is not None and tenant.id is not None
        changed = 0
        storefront = state.storefront
        if storefront is None:
            storefront = Storefront(
                tenant_id=int(tenant.id),
                **OrshaStorefrontDefinition.storefront_target(),
            )
            session.add(storefront)
            await session.flush()
            cls._add_audit(
                session,
                tenant_id=int(tenant.id),
                storefront_id=int(storefront.id),
                entity_type="storefront",
                entity_id=int(storefront.id),
                action="storefront.canary_created",
                change_set=cls._creation_change_set(
                    OrshaStorefrontDefinition.storefront_target()
                ),
                request_id=request_id,
            )
            changed += 1
        else:
            change_set = cls._apply_model_changes(storefront, {"status": "draft"})
            if change_set:
                cls._add_audit(
                    session,
                    tenant_id=int(tenant.id),
                    storefront_id=int(storefront.id),
                    entity_type="storefront",
                    entity_id=int(storefront.id),
                    action="storefront.canary_prepared",
                    change_set=change_set,
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
            cls._add_audit(
                session,
                tenant_id=int(tenant.id),
                storefront_id=int(storefront.id),
                entity_type="storefront_domain",
                entity_id=int(domain.id),
                action="storefront_domain.canary_created",
                change_set=cls._creation_change_set(
                    {
                        "hostname": hostname,
                        "status": "pending",
                        "is_primary": True,
                    }
                ),
                request_id=request_id,
            )
            changed += 1
        else:
            change_set = cls._apply_model_changes(domain, {"status": "pending"})
            if change_set:
                cls._add_audit(
                    session,
                    tenant_id=int(tenant.id),
                    storefront_id=int(storefront.id),
                    entity_type="storefront_domain",
                    entity_id=int(domain.id),
                    action="storefront_domain.canary_prepared",
                    change_set=change_set,
                    request_id=request_id,
                )
                changed += 1

        tenant_scope = TenantScope(
            tenant_id=int(tenant.id),
            storefront_id=int(storefront.id),
            is_system=True,
            is_canonical_storefront=False,
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
                actor_username=OrshaStorefrontDefinition.ACTOR_USERNAME,
                actor_staff_user_id=None,
                request_id=request_id,
                stage_catalog_invalidation=False,
            )
            changed += int(mutation.changed)
        return changed, False

    @classmethod
    async def _stage_activate(
        cls,
        session: AsyncSession,
        *,
        state: LoadedOrshaStorefrontState,
        request_id: str,
    ) -> tuple[int, bool]:
        tenant = state.tenant
        storefront = state.storefront
        domain = state.domains[0]
        assert tenant is not None and tenant.id is not None
        assert storefront is not None and storefront.id is not None
        now = datetime.now(timezone.utc)
        storefront_changes = cls._apply_model_changes(
            storefront,
            {"status": "active"},
        )
        domain_target: dict[str, Any] = {"status": "active"}
        if domain.status != "active":
            domain_target["verified_at"] = now
        domain_changes = cls._apply_model_changes(domain, domain_target)
        changed = 0
        for entity, entity_type, action, change_set in (
            (
                storefront,
                "storefront",
                "storefront.canary_activated",
                storefront_changes,
            ),
            (
                domain,
                "storefront_domain",
                "storefront_domain.canary_activated",
                domain_changes,
            ),
        ):
            if not change_set:
                continue
            cls._add_audit(
                session,
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
                state=state,
                reason="orsha_storefront_activated",
            )
        return changed, invalidation_staged

    @classmethod
    async def _stage_disable(
        cls,
        session: AsyncSession,
        *,
        state: LoadedOrshaStorefrontState,
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
        domain = state.domains[0] if state.domains else None
        routable = (
            storefront.status == "active"
            and domain is not None
            and domain.status == "active"
        )
        needs_change = (
            storefront.status != "disabled"
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
                state=state,
                reason="orsha_storefront_disabled",
            )

        tenant_scope = TenantScope(
            tenant_id=int(tenant.id),
            storefront_id=int(storefront.id),
            is_system=True,
            is_canonical_storefront=False,
        )
        changed = 0
        for offer, _ in state.offers:
            mutation = await TenantOfferMutationStagingService.stage_update(
                session,
                offer_id=int(offer.id),
                payload={"status": "disabled", "is_published": False},
                tenant_scope=tenant_scope,
                actor_username=OrshaStorefrontDefinition.ACTOR_USERNAME,
                actor_staff_user_id=None,
                request_id=request_id,
                stage_catalog_invalidation=False,
            )
            changed += int(mutation.changed)

        if domain is not None:
            domain_changes = cls._apply_model_changes(
                domain,
                {"status": "disabled"},
            )
            if domain_changes:
                cls._add_audit(
                    session,
                    tenant_id=int(tenant.id),
                    storefront_id=int(storefront.id),
                    entity_type="storefront_domain",
                    entity_id=int(domain.id),
                    action="storefront_domain.canary_disabled",
                    change_set=domain_changes,
                    request_id=request_id,
                )
                changed += 1
        storefront_changes = cls._apply_model_changes(
            storefront,
            {"status": "disabled"},
        )
        if storefront_changes:
            cls._add_audit(
                session,
                tenant_id=int(tenant.id),
                storefront_id=int(storefront.id),
                entity_type="storefront",
                entity_id=int(storefront.id),
                action="storefront.canary_disabled",
                change_set=storefront_changes,
                request_id=request_id,
            )
            changed += 1
        return changed, invalidation_staged

    @staticmethod
    async def _stage_catalog_invalidation(
        session: AsyncSession,
        *,
        state: LoadedOrshaStorefrontState,
        reason: str,
    ) -> bool:
        tenant = state.tenant
        storefront = state.storefront
        assert tenant is not None and tenant.id is not None
        assert storefront is not None and storefront.id is not None
        return await TenantOfferCatalogInvalidationAdapter.stage(
            session,
            reason=reason,
            tenant_scope=TenantScope(
                tenant_id=int(tenant.id),
                storefront_id=int(storefront.id),
                is_system=True,
                is_canonical_storefront=False,
            ),
            product_ids=[int(product.id) for _, product in state.offers],
            slugs=[product.slug for _, product in state.offers],
            required=True,
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
                actor_username=OrshaStorefrontDefinition.ACTOR_USERNAME,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                request_id=request_id,
                change_set=change_set,
            )
        )
