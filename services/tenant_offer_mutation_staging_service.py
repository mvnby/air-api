from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.request_context import current_request_id
from crud.tenant_offer import TenantOfferDAO
from models import Product, TenantAuditEvent, TenantOffer
from models.tenancy import TenantScope
from services.tenant_offer_catalog_invalidation import (
    TenantOfferCatalogInvalidationAdapter,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class TenantOfferMutation:
    offer: TenantOffer
    product: Product
    action: str | None
    change_set: dict[str, dict[str, Any]]
    invalidation_staged: bool

    @property
    def changed(self) -> bool:
        return bool(self.change_set)


class TenantOfferMutationStagingService:
    """Stage one offer and audit record without owning commit or rollback."""

    @classmethod
    async def stage_upsert(
        cls,
        session: AsyncSession,
        *,
        payload: dict[str, Any],
        tenant_scope: TenantScope,
        actor_username: str,
        actor_staff_user_id: int | None,
        request_id: str | None = None,
        stage_catalog_invalidation: bool = True,
    ) -> TenantOfferMutation:
        if (
            await TenantOfferDAO.lock_scope_storefront(
                session,
                tenant_scope=tenant_scope,
            )
            is None
        ):
            raise HTTPException(status_code=404, detail="Витрина не найдена.")
        product_id = int(payload["product_id"])
        product = await TenantOfferDAO.lock_product(session, product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="Товар не найден.")

        offer = await TenantOfferDAO.get_by_product_for_scope(
            session,
            product_id=product_id,
            tenant_scope=tenant_scope,
            for_update=True,
        )
        normalized = cls.normalize_fields(payload)
        if offer is None:
            offer = TenantOffer(
                tenant_id=tenant_scope.tenant_id,
                storefront_id=tenant_scope.storefront_id,
                product_id=product_id,
                created_by_username=actor_username,
                updated_by_username=actor_username,
                **normalized,
            )
            TenantOfferDAO.add_offer(session, offer)
            await session.flush()
            change_set = {
                field: {"before": None, "after": value}
                for field, value in normalized.items()
            }
            action = "tenant_offer.created"
        else:
            change_set = cls.apply_changes(
                offer,
                normalized,
                actor_username=actor_username,
            )
            action = "tenant_offer.updated" if change_set else None

        return await cls._finish(
            session,
            offer=offer,
            product=product,
            tenant_scope=tenant_scope,
            actor_username=actor_username,
            actor_staff_user_id=actor_staff_user_id,
            request_id=request_id,
            action=action,
            change_set=change_set,
            stage_catalog_invalidation=stage_catalog_invalidation,
        )

    @classmethod
    async def stage_update(
        cls,
        session: AsyncSession,
        *,
        offer_id: int,
        payload: dict[str, Any],
        tenant_scope: TenantScope,
        actor_username: str,
        actor_staff_user_id: int | None,
        request_id: str | None = None,
        stage_catalog_invalidation: bool = True,
    ) -> TenantOfferMutation:
        if (
            await TenantOfferDAO.lock_scope_storefront(
                session,
                tenant_scope=tenant_scope,
            )
            is None
        ):
            raise HTTPException(status_code=404, detail="Витрина не найдена.")
        offer = await TenantOfferDAO.get_for_scope(
            session,
            offer_id=offer_id,
            tenant_scope=tenant_scope,
            for_update=True,
        )
        if offer is None:
            raise HTTPException(status_code=404, detail="Предложение не найдено.")
        product = await TenantOfferDAO.get_product(session, offer.product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="Товар не найден.")

        normalized = cls.normalize_fields(
            {
                "price": payload.get("price", offer.price),
                "old_price": (
                    payload["old_price"]
                    if "old_price" in payload
                    else offer.old_price
                ),
                "is_published": payload.get("is_published", offer.is_published),
                "status": payload.get("status", offer.status),
            }
        )
        change_set = cls.apply_changes(
            offer,
            normalized,
            actor_username=actor_username,
        )
        return await cls._finish(
            session,
            offer=offer,
            product=product,
            tenant_scope=tenant_scope,
            actor_username=actor_username,
            actor_staff_user_id=actor_staff_user_id,
            request_id=request_id,
            action="tenant_offer.updated" if change_set else None,
            change_set=change_set,
            stage_catalog_invalidation=stage_catalog_invalidation,
        )

    @classmethod
    async def _finish(
        cls,
        session: AsyncSession,
        *,
        offer: TenantOffer,
        product: Product,
        tenant_scope: TenantScope,
        actor_username: str,
        actor_staff_user_id: int | None,
        request_id: str | None,
        action: str | None,
        change_set: dict[str, dict[str, Any]],
        stage_catalog_invalidation: bool,
    ) -> TenantOfferMutation:
        invalidation_staged = False
        if action:
            TenantOfferDAO.add_audit_event(
                session,
                cls.audit_event(
                    offer=offer,
                    tenant_scope=tenant_scope,
                    actor_username=actor_username,
                    actor_staff_user_id=actor_staff_user_id,
                    request_id=request_id,
                    action=action,
                    change_set=change_set,
                ),
            )
            if stage_catalog_invalidation:
                invalidation_staged = (
                    await TenantOfferCatalogInvalidationAdapter.stage(
                        session,
                        reason=action.replace(".", "_"),
                        tenant_scope=tenant_scope,
                        product_ids=[int(product.id)],
                        slugs=[product.slug],
                    )
                )
        await session.flush()
        return TenantOfferMutation(
            offer=offer,
            product=product,
            action=action,
            change_set=change_set,
            invalidation_staged=invalidation_staged,
        )

    @staticmethod
    def normalize_fields(payload: dict[str, Any]) -> dict[str, Any]:
        price = int(payload["price"])
        old_price_raw = payload.get("old_price")
        old_price = int(old_price_raw) if old_price_raw is not None else None
        if price < 0 or (old_price is not None and old_price < price):
            raise HTTPException(
                status_code=422,
                detail="Старая цена не может быть ниже текущей цены.",
            )
        status = str(payload.get("status") or "active")
        if status not in {"active", "disabled"}:
            raise HTTPException(
                status_code=422,
                detail="Недопустимый статус предложения.",
            )
        is_published = bool(payload.get("is_published", False))
        if status == "disabled":
            is_published = False
        return {
            "price": price,
            "old_price": old_price,
            "is_published": is_published,
            "status": status,
        }

    @staticmethod
    def apply_changes(
        offer: TenantOffer,
        values: dict[str, Any],
        *,
        actor_username: str,
    ) -> dict[str, dict[str, Any]]:
        change_set: dict[str, dict[str, Any]] = {}
        for field, after in values.items():
            before = getattr(offer, field)
            if before != after:
                change_set[field] = {"before": before, "after": after}
                setattr(offer, field, after)
        if change_set:
            offer.updated_by_username = actor_username
            offer.updated_at = utc_now()
        return change_set

    @staticmethod
    def audit_event(
        *,
        offer: TenantOffer,
        tenant_scope: TenantScope,
        actor_username: str,
        actor_staff_user_id: int | None,
        request_id: str | None,
        action: str,
        change_set: dict[str, Any],
    ) -> TenantAuditEvent:
        return TenantAuditEvent(
            tenant_id=tenant_scope.tenant_id,
            storefront_id=tenant_scope.storefront_id,
            actor_staff_user_id=actor_staff_user_id,
            actor_username=actor_username,
            action=action,
            entity_type="tenant_offer",
            entity_id=int(offer.id),
            request_id=str(request_id or current_request_id()),
            change_set=change_set,
        )
