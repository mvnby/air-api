from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import (
    ProductCollection,
    ProductCollectionItem,
    ProductCollectionPlacement,
)


class ProductCollectionDAO:
    @staticmethod
    async def list_all(session: AsyncSession) -> list[ProductCollection]:
        result = await session.execute(
            select(ProductCollection)
            .options(
                selectinload(ProductCollection.items).selectinload(ProductCollectionItem.product),
                selectinload(ProductCollection.placements),
            )
            .order_by(ProductCollection.updated_at.desc(), ProductCollection.id.desc())
            .execution_options(populate_existing=True)
        )
        return list(result.scalars().unique().all())

    @staticmethod
    async def get(
        session: AsyncSession,
        collection_id: int,
    ) -> ProductCollection | None:
        result = await session.execute(
            select(ProductCollection)
            .where(ProductCollection.id == collection_id)
            .options(
                selectinload(ProductCollection.items).selectinload(ProductCollectionItem.product),
                selectinload(ProductCollection.placements),
            )
            .execution_options(populate_existing=True)
        )
        return result.scalars().unique().one_or_none()

    @staticmethod
    async def get_by_slug(
        session: AsyncSession,
        slug: str,
    ) -> ProductCollection | None:
        result = await session.execute(
            select(ProductCollection).where(ProductCollection.slug == slug)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_placements(
        session: AsyncSession,
        *,
        surface_key: str,
        slot_key: str,
        now: datetime,
    ) -> list[tuple[ProductCollectionPlacement, ProductCollection]]:
        result = await session.execute(
            select(ProductCollectionPlacement, ProductCollection)
            .join(
                ProductCollection,
                ProductCollection.id == ProductCollectionPlacement.collection_id,
            )
            .where(
                ProductCollectionPlacement.surface_key == surface_key,
                ProductCollectionPlacement.slot_key == slot_key,
                ProductCollectionPlacement.is_enabled.is_(True),
                ProductCollection.status == "published",
                (ProductCollection.starts_at.is_(None) | (ProductCollection.starts_at <= now)),
                (ProductCollection.ends_at.is_(None) | (ProductCollection.ends_at > now)),
                (
                    ProductCollectionPlacement.starts_at.is_(None)
                    | (ProductCollectionPlacement.starts_at <= now)
                ),
                (
                    ProductCollectionPlacement.ends_at.is_(None)
                    | (ProductCollectionPlacement.ends_at > now)
                ),
            )
            .order_by(
                ProductCollectionPlacement.position.asc(),
                ProductCollectionPlacement.id.asc(),
            )
        )
        return list(result.all())

    @staticmethod
    async def list_items(
        session: AsyncSession,
        collection_id: int,
    ) -> list[ProductCollectionItem]:
        result = await session.execute(
            select(ProductCollectionItem)
            .where(ProductCollectionItem.collection_id == collection_id)
            .order_by(ProductCollectionItem.position.asc(), ProductCollectionItem.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def replace_items(
        session: AsyncSession,
        *,
        collection_id: int,
        items: list[dict],
    ) -> None:
        await session.execute(
            delete(ProductCollectionItem).where(
                ProductCollectionItem.collection_id == collection_id
            )
        )
        await session.flush()
        for position, payload in enumerate(items):
            session.add(
                ProductCollectionItem(
                    collection_id=collection_id,
                    product_id=int(payload["product_id"]),
                    position=position,
                    is_pinned=bool(payload.get("is_pinned", True)),
                    editorial_note=payload.get("editorial_note"),
                )
            )
        await session.flush()

    @staticmethod
    async def replace_placements(
        session: AsyncSession,
        *,
        collection_id: int,
        placements: list[dict],
    ) -> None:
        await session.execute(
            delete(ProductCollectionPlacement).where(
                ProductCollectionPlacement.collection_id == collection_id
            )
        )
        await session.flush()
        for payload in placements:
            session.add(
                ProductCollectionPlacement(
                    collection_id=collection_id,
                    **payload,
                )
            )
        await session.flush()
