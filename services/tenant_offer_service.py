from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from crud.tenant_offer import TenantOfferDAO
from models import Product, TenantOffer
from models.tenancy import TenantScope
from services.tenant_offer_mutation_staging_service import (
    TenantOfferMutationStagingService,
)


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
            mutation = await TenantOfferMutationStagingService.stage_upsert(
                session,
                payload=payload,
                tenant_scope=tenant_scope,
                actor_username=actor_username,
                actor_staff_user_id=actor_staff_user_id,
            )
            await session.commit()
            return cls._serialize_offer(mutation.offer, mutation.product)
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
            mutation = await TenantOfferMutationStagingService.stage_update(
                session,
                offer_id=offer_id,
                payload=payload,
                tenant_scope=tenant_scope,
                actor_username=actor_username,
                actor_staff_user_id=actor_staff_user_id,
            )
            if mutation.changed:
                await session.commit()
            return cls._serialize_offer(mutation.offer, mutation.product)
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
