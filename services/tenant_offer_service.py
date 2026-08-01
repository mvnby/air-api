from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.request_context import current_request_id
from crud.tenant_offer import TenantOfferDAO
from models import Product, TenantAuditEvent, TenantOffer
from models.tenancy import TenantScope


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TenantOfferService:
    @classmethod
    async def list_offers(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        offset: int,
        limit: int,
    ) -> dict:
        rows, total = await TenantOfferDAO.list_for_scope(
            session,
            tenant_scope=tenant_scope,
            offset=offset,
            limit=limit,
        )
        return {
            "items": [cls._serialize_offer(offer, product) for offer, product in rows],
            "total": total,
        }

    @classmethod
    async def get_offer(
        cls,
        session: AsyncSession,
        *,
        offer_id: int,
        tenant_scope: TenantScope,
    ) -> dict:
        offer = await TenantOfferDAO.get_for_scope(
            session,
            offer_id=offer_id,
            tenant_scope=tenant_scope,
        )
        if offer is None:
            raise HTTPException(status_code=404, detail="Предложение не найдено.")
        product = await TenantOfferDAO.get_product(session, offer.product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="Товар не найден.")
        return cls._serialize_offer(offer, product)

    @classmethod
    async def upsert_offer(
        cls,
        session: AsyncSession,
        *,
        payload: dict[str, Any],
        tenant_scope: TenantScope,
        actor_username: str,
        actor_staff_user_id: int | None,
    ) -> dict:
        try:
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
            normalized = cls._normalize_offer_fields(payload)
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
                change_set = cls._apply_changes(
                    offer,
                    normalized,
                    actor_username=actor_username,
                )
                action = "tenant_offer.updated"

            if change_set:
                TenantOfferDAO.add_audit_event(
                    session,
                    cls._audit_event(
                        offer=offer,
                        tenant_scope=tenant_scope,
                        actor_username=actor_username,
                        actor_staff_user_id=actor_staff_user_id,
                        action=action,
                        change_set=change_set,
                    ),
                )
            await session.commit()
            return cls._serialize_offer(offer, product)
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=409,
                detail="Предложение было изменено параллельно. Повторите запрос.",
            ) from exc
        except HTTPException:
            # Validation/not-found paths have not mutated persistence state.
            # Let the request-owned session close its read transaction instead
            # of rolling back a caller-managed transaction boundary.
            raise
        except Exception:
            await session.rollback()
            raise

    @classmethod
    async def update_offer(
        cls,
        session: AsyncSession,
        *,
        offer_id: int,
        payload: dict[str, Any],
        tenant_scope: TenantScope,
        actor_username: str,
        actor_staff_user_id: int | None,
    ) -> dict:
        try:
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

            normalized = cls._normalize_offer_fields(
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
            change_set = cls._apply_changes(
                offer,
                normalized,
                actor_username=actor_username,
            )
            if change_set:
                TenantOfferDAO.add_audit_event(
                    session,
                    cls._audit_event(
                        offer=offer,
                        tenant_scope=tenant_scope,
                        actor_username=actor_username,
                        actor_staff_user_id=actor_staff_user_id,
                        action="tenant_offer.updated",
                        change_set=change_set,
                    ),
                )
                await session.commit()
            return cls._serialize_offer(offer, product)
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=409,
                detail="Предложение было изменено параллельно. Повторите запрос.",
            ) from exc
        except HTTPException:
            raise
        except Exception:
            await session.rollback()
            raise

    @staticmethod
    async def list_audit_events(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        offset: int,
        limit: int,
    ) -> dict:
        rows, total = await TenantOfferDAO.list_audit_for_scope(
            session,
            tenant_scope=tenant_scope,
            offset=offset,
            limit=limit,
        )
        return {
            "items": [
                {
                    "id": int(event.id),
                    "storefront_id": event.storefront_id,
                    "actor_staff_user_id": event.actor_staff_user_id,
                    "actor_username": event.actor_username,
                    "action": event.action,
                    "entity_type": event.entity_type,
                    "entity_id": event.entity_id,
                    "request_id": event.request_id,
                    "change_set": event.change_set,
                    "created_at": event.created_at,
                }
                for event in rows
            ],
            "total": total,
        }

    @staticmethod
    def _normalize_offer_fields(payload: dict[str, Any]) -> dict[str, Any]:
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
            raise HTTPException(status_code=422, detail="Недопустимый статус предложения.")
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
    def _apply_changes(
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
    def _audit_event(
        *,
        offer: TenantOffer,
        tenant_scope: TenantScope,
        actor_username: str,
        actor_staff_user_id: int | None,
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
            request_id=current_request_id(),
            change_set=change_set,
        )

    @staticmethod
    def _serialize_offer(offer: TenantOffer, product: Product) -> dict:
        return {
            "id": int(offer.id),
            "storefront_id": offer.storefront_id,
            "product_id": offer.product_id,
            "product_title": product.title,
            "product_slug": product.slug,
            "price": offer.price,
            "old_price": offer.old_price,
            "is_published": offer.is_published,
            "status": offer.status,
            "created_by_username": offer.created_by_username,
            "updated_by_username": offer.updated_by_username,
            "created_at": offer.created_at,
            "updated_at": offer.updated_at,
        }
