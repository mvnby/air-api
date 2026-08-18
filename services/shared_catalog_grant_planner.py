from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from crud.shared_catalog_grant import SharedCatalogGrantDAO
from models import Product, Storefront, Tenant, TenantCatalogGrant, TenantOffer
from services.shared_catalog_grant_manifest import SharedCatalogGrantManifest


class SharedCatalogGrantBlockedError(RuntimeError):
    pass


@dataclass
class SharedCatalogGrantState:
    tenant: Tenant | None
    storefront: Storefront | None
    grant: TenantCatalogGrant | None
    rows: list[tuple[Product, TenantOffer | None]]


class SharedCatalogGrantPlanner:
    STATUSES = frozenset({"active", "disabled"})

    @classmethod
    async def build(
        cls,
        session: AsyncSession,
        *,
        desired_status: str,
        manifest: SharedCatalogGrantManifest,
        for_update: bool,
    ) -> tuple[dict[str, Any], SharedCatalogGrantState]:
        status = cls.normalize_status(desired_status)
        scope = await SharedCatalogGrantDAO.get_scope(
            session,
            tenant_slug=manifest.tenant_slug,
            storefront_slug=manifest.storefront_slug,
            for_update=for_update,
        )
        tenant = scope[0] if scope is not None else None
        storefront = scope[1] if scope is not None else None
        grant = None
        rows: list[tuple[Product, TenantOffer | None]] = []
        blockers: list[str] = []
        if tenant is None or storefront is None:
            blockers.append("tenant/storefront scope does not exist")
        else:
            grant = await SharedCatalogGrantDAO.get_grant(
                session,
                tenant_id=int(tenant.id),
                storefront_id=int(storefront.id),
                for_update=for_update,
            )
            rows = await SharedCatalogGrantDAO.list_projection_rows(
                session,
                tenant_id=int(tenant.id),
                storefront_id=int(storefront.id),
                grant_id=int(grant.id) if grant is not None else None,
                desired_status=status,
            )
            blockers.extend(
                cls._scope_blockers(
                    tenant=tenant,
                    storefront=storefront,
                    grant=grant,
                    desired_status=status,
                    manifest=manifest,
                )
            )

        offer_changes, offer_blockers = cls._offer_changes(
            rows=rows,
            grant=grant,
            desired_status=status,
        )
        blockers.extend(offer_blockers)
        batch = offer_changes[: manifest.batch_size]
        has_more = len(offer_changes) > len(batch)
        grant_change = cls._grant_change(
            grant=grant,
            desired_status=status,
            has_more=has_more,
            offer_change_count=len(offer_changes),
        )
        action_fingerprint = cls._digest_value(offer_changes)
        state = SharedCatalogGrantState(
            tenant=tenant,
            storefront=storefront,
            grant=grant,
            rows=rows,
        )
        plan_without_digest = {
            "mode": "plan",
            "desired_status": status,
            "manifest_fingerprint": manifest.fingerprint,
            "tenant_slug": manifest.tenant_slug,
            "storefront_slug": manifest.storefront_slug,
            "policy": {
                "mode": manifest.mode,
                "price_policy": manifest.price_policy,
                "owner_type": manifest.owner_type,
            },
            "batch_size": manifest.batch_size,
            "ready": not blockers,
            "blockers": list(dict.fromkeys(blockers)),
            "scope": cls._serialize_scope(tenant, storefront),
            "grant": cls._serialize_grant(grant),
            "grant_change": grant_change,
            "offer_change_count": len(offer_changes),
            "batch_change_count": len(batch),
            "has_more": has_more,
            "offer_changes_fingerprint": action_fingerprint,
            "batch_changes": batch,
        }
        return (
            {
                **plan_without_digest,
                "plan_digest": cls._digest_value(plan_without_digest),
            },
            state,
        )

    @classmethod
    def _scope_blockers(
        cls,
        *,
        tenant: Tenant,
        storefront: Storefront,
        grant: TenantCatalogGrant | None,
        desired_status: str,
        manifest: SharedCatalogGrantManifest,
    ) -> list[str]:
        blockers: list[str] = []
        if tenant.is_system:
            blockers.append("shared catalog grants are only for non-system tenants")
        if desired_status == "active":
            if tenant.status != "active":
                blockers.append("tenant must be active before catalog grant sync")
            if storefront.status not in {"draft", "active"}:
                blockers.append("storefront must be bootstrapped before catalog grant sync")
            if (
                storefront.status == "active"
                and (grant is None or grant.status != "active")
            ):
                blockers.append(
                    "initial grant activation requires a non-routable draft storefront"
                )
        if grant is not None:
            expected = {
                "mode": manifest.mode,
                "price_policy": manifest.price_policy,
                "owner_type": manifest.owner_type,
            }
            for field, value in expected.items():
                if getattr(grant, field) != value:
                    blockers.append(f"grant {field} differs from reviewed policy")
        return blockers

    @classmethod
    def _offer_changes(
        cls,
        *,
        rows: list[tuple[Product, TenantOffer | None]],
        grant: TenantCatalogGrant | None,
        desired_status: str,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        changes: list[dict[str, Any]] = []
        blockers: list[str] = []
        grant_id: int | str = (
            int(grant.id) if grant is not None else "created-on-execute"
        )
        for product, offer in rows:
            product_id = int(product.id)
            if product.is_published and (
                int(product.price) < 0
                or (
                    product.old_price is not None
                    and int(product.old_price) < int(product.price)
                )
            ):
                blockers.append(
                    f"product {product_id} has invalid master price semantics"
                )
                continue
            if (
                offer is not None
                and offer.catalog_grant_id is not None
                and grant is not None
                and offer.catalog_grant_id != grant.id
            ):
                blockers.append(
                    f"product {product_id} is linked to another catalog grant"
                )
                continue
            if desired_status == "active" and product.is_published:
                target: dict[str, Any] = {
                    "catalog_grant_id": grant_id,
                    "status": "active",
                    "is_published": True,
                }
                if offer is None:
                    target.update(
                        {
                            "price": int(product.price),
                            "old_price": (
                                int(product.old_price)
                                if product.old_price is not None
                                else None
                            ),
                            "price_source": "inherited_master",
                        }
                    )
                    changes.append(
                        {
                            "operation": "create",
                            "product_id": product_id,
                            "product_slug": product.slug,
                            "before": None,
                            "after": target,
                        }
                    )
                    continue
                if offer.price_source == "inherited_master":
                    target.update(
                        {
                            "price": int(product.price),
                            "old_price": (
                                int(product.old_price)
                                if product.old_price is not None
                                else None
                            ),
                        }
                    )
            elif offer is not None and (
                grant is not None and offer.catalog_grant_id == grant.id
            ):
                target = {"status": "disabled", "is_published": False}
            else:
                continue

            assert offer is not None
            fields = {
                field: {
                    "before": cls._value(getattr(offer, field)),
                    "after": cls._value(value),
                }
                for field, value in target.items()
                if getattr(offer, field) != value
            }
            if fields:
                changes.append(
                    {
                        "operation": "update",
                        "offer_id": int(offer.id),
                        "product_id": product_id,
                        "product_slug": product.slug,
                        "fields": fields,
                    }
                )
        changes.sort(key=lambda item: (int(item["product_id"]), item["operation"]))
        return changes, blockers

    @staticmethod
    def _grant_change(
        *,
        grant: TenantCatalogGrant | None,
        desired_status: str,
        has_more: bool,
        offer_change_count: int,
    ) -> dict[str, Any] | None:
        if grant is None:
            if desired_status == "disabled":
                return None
            target = "syncing" if has_more else "active"
            return {"operation": "create", "before": None, "after_status": target}
        if desired_status == "disabled":
            if grant.status == "disabled":
                return None
            return {
                "operation": "update",
                "before_status": grant.status,
                "after_status": "disabled",
            }
        if grant.status == "disabled":
            return {
                "operation": "update",
                "before_status": "disabled",
                "after_status": "syncing" if has_more else "active",
            }
        if grant.status == "syncing" and not has_more and offer_change_count == 0:
            return {
                "operation": "update",
                "before_status": "syncing",
                "after_status": "active",
            }
        if grant.status == "syncing" and not has_more:
            return {
                "operation": "update",
                "before_status": "syncing",
                "after_status": "active",
            }
        return None

    @staticmethod
    def _serialize_scope(
        tenant: Tenant | None,
        storefront: Storefront | None,
    ) -> dict[str, Any] | None:
        if tenant is None or storefront is None:
            return None
        return {
            "tenant_id": int(tenant.id),
            "tenant_status": tenant.status,
            "tenant_is_system": tenant.is_system,
            "storefront_id": int(storefront.id),
            "storefront_status": storefront.status,
        }

    @classmethod
    def _serialize_grant(
        cls,
        grant: TenantCatalogGrant | None,
    ) -> dict[str, Any] | None:
        if grant is None:
            return None
        return {
            "id": int(grant.id),
            "mode": grant.mode,
            "price_policy": grant.price_policy,
            "owner_type": grant.owner_type,
            "status": grant.status,
            "revision": grant.revision,
            "last_completed_sync_at": cls._value(grant.last_completed_sync_at),
            "last_completed_sync_fingerprint": (
                grant.last_completed_sync_fingerprint
            ),
            "updated_at": cls._value(grant.updated_at),
        }

    @staticmethod
    def normalize_status(value: str) -> str:
        normalized = str(value or "").strip().casefold()
        if normalized not in SharedCatalogGrantPlanner.STATUSES:
            raise ValueError("desired status must be active or disabled")
        return normalized

    @staticmethod
    def _digest_value(value: Any) -> str:
        return hashlib.sha256(
            json.dumps(
                value,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _value(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        return value


__all__ = [
    "SharedCatalogGrantBlockedError",
    "SharedCatalogGrantPlanner",
    "SharedCatalogGrantState",
]
