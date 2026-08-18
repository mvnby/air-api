from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from crud.shared_catalog_grant import SharedCatalogGrantDAO
from models import TenantAuditEvent, TenantCatalogGrant, TenantOffer
from models.tenancy import TenantScope
from services.shared_catalog_grant_manifest import SharedCatalogGrantManifest
from services.shared_catalog_grant_planner import SharedCatalogGrantState
from services.tenant_offer_catalog_invalidation import (
    TenantOfferCatalogInvalidationAdapter,
)


class SharedCatalogGrantStagingService:
    @classmethod
    async def stage(
        cls,
        session: AsyncSession,
        *,
        plan: dict[str, Any],
        state: SharedCatalogGrantState,
        manifest: SharedCatalogGrantManifest,
        request_id: str,
    ) -> dict[str, Any]:
        tenant = state.tenant
        storefront = state.storefront
        assert tenant is not None and storefront is not None
        now = datetime.now(timezone.utc)
        grant = state.grant
        grant_change = plan["grant_change"]
        grant_before_status = grant.status if grant is not None else None
        if grant is None:
            if grant_change is None:
                return {
                    "changed": False,
                    "grant": None,
                    "offer_changes": 0,
                    "catalog_invalidation_staged": False,
                }
            grant = TenantCatalogGrant(
                tenant_id=int(tenant.id),
                storefront_id=int(storefront.id),
                mode=manifest.mode,
                price_policy=manifest.price_policy,
                owner_type=manifest.owner_type,
                status=str(grant_change["after_status"]),
                revision=1,
                created_by_username=manifest.actor_username,
                updated_by_username=manifest.actor_username,
                created_at=now,
                updated_at=now,
            )
            session.add(grant)
            await session.flush()
        elif grant_change is not None:
            grant.status = str(grant_change["after_status"])

        assert grant.id is not None
        rows_by_product = {int(product.id): (product, offer) for product, offer in state.rows}
        applied_changes: list[dict[str, Any]] = []
        affected_products: dict[int, str] = {}
        for change in plan["batch_changes"]:
            product_id = int(change["product_id"])
            product, offer = rows_by_product[product_id]
            if change["operation"] == "create":
                after = dict(change["after"])
                after["catalog_grant_id"] = int(grant.id)
                offer = TenantOffer(
                    tenant_id=int(tenant.id),
                    storefront_id=int(storefront.id),
                    product_id=product_id,
                    catalog_grant_id=int(grant.id),
                    price=int(after["price"]),
                    old_price=after["old_price"],
                    is_published=bool(after["is_published"]),
                    status=str(after["status"]),
                    price_source=str(after["price_source"]),
                    created_by_username=manifest.actor_username,
                    updated_by_username=manifest.actor_username,
                    created_at=now,
                    updated_at=now,
                )
                session.add(offer)
                await session.flush()
                applied_changes.append(
                    {
                        **change,
                        "offer_id": int(offer.id),
                        "after": after,
                    }
                )
            else:
                assert offer is not None
                exact_fields: dict[str, dict[str, Any]] = {}
                for field, values in change["fields"].items():
                    after = values["after"]
                    if field == "catalog_grant_id":
                        after = int(grant.id)
                    before = getattr(offer, field)
                    setattr(offer, field, after)
                    exact_fields[field] = {"before": before, "after": after}
                offer.updated_by_username = manifest.actor_username
                offer.updated_at = now
                applied_changes.append({**change, "fields": exact_fields})
            affected_products[product_id] = product.slug

        changed = bool(grant_change or applied_changes)
        if changed:
            if state.grant is not None:
                grant.revision = int(grant.revision) + 1
            grant.updated_by_username = manifest.actor_username
            grant.updated_at = now
            if not plan["has_more"]:
                grant.last_completed_sync_at = now
                grant.last_completed_sync_fingerprint = plan["plan_digest"]
            SharedCatalogGrantDAO.add_audit_event(
                session,
                TenantAuditEvent(
                    tenant_id=int(tenant.id),
                    storefront_id=int(storefront.id),
                    actor_staff_user_id=None,
                    actor_username=manifest.actor_username,
                    action="tenant_catalog_grant.synced",
                    entity_type="tenant_catalog_grant",
                    entity_id=int(grant.id),
                    request_id=request_id,
                    change_set={
                        "desired_status": plan["desired_status"],
                        "grant_status": {
                            "before": grant_before_status,
                            "after": grant.status,
                        },
                        "grant_revision": grant.revision,
                        "batch_changes": applied_changes,
                        "remaining_after_batch": (
                            plan["offer_change_count"] - len(applied_changes)
                        ),
                        "reviewed_plan_digest": plan["plan_digest"],
                        "manifest_fingerprint": manifest.fingerprint,
                    },
                ),
            )
            await session.flush()

        visibility_flip = (
            grant_before_status != grant.status
            and "active" in {grant_before_status, grant.status}
        )
        if visibility_flip:
            affected_products = {
                int(product.id): product.slug for product, _offer in state.rows
            }
        invalidation_staged = False
        if changed and storefront.status == "active":
            invalidation_staged = await TenantOfferCatalogInvalidationAdapter.stage(
                session,
                reason="shared_catalog_grant_sync",
                tenant_scope=TenantScope(
                    tenant_id=int(tenant.id),
                    storefront_id=int(storefront.id),
                    is_system=False,
                    is_canonical_storefront=False,
                ),
                product_ids=affected_products,
                slugs=affected_products.values(),
            )
        await session.flush()
        return {
            "changed": changed,
            "grant": grant,
            "offer_changes": len(applied_changes),
            "catalog_invalidation_staged": invalidation_staged,
        }


__all__ = ["SharedCatalogGrantStagingService"]
