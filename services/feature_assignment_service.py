from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import delete, select

from models import (
    Brand,
    Feature,
    FeatureBrandLink,
    FeatureProductLink,
    FeatureSeriesLink,
    MediaAsset,
    Product,
    ProductSeries,
)
from schemas_features import (
    FeatureLinkPayload,
    FeatureTargetLinkPayload,
    ManagerProductFeatureWorkspaceResponse,
)
from services.catalog_revision_service import CatalogRevisionService
from services.feature_resolver_service import FeatureResolverService


class FeatureAssignmentService:
    @staticmethod
    async def get_product_workspace(
        session: AsyncSession,
        product_id: int,
    ) -> ManagerProductFeatureWorkspaceResponse:
        product = await session.get(Product, product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="Товар не найден")
        result = await FeatureResolverService.resolve_for_products(
            session, [product], include_suggestions=True
        )
        return ManagerProductFeatureWorkspaceResponse(**result[int(product.id)])

    @staticmethod
    async def replace_product_assignments(
        session: AsyncSession,
        product_id: int,
        assignments: list[FeatureLinkPayload],
    ) -> ManagerProductFeatureWorkspaceResponse:
        product = await session.get(Product, product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="Товар не найден")
        feature_ids = [item.feature_id for item in assignments]
        if len(feature_ids) != len(set(feature_ids)):
            raise HTTPException(status_code=400, detail="Фича не может быть назначена товару дважды")
        await FeatureAssignmentService._validate_features(session, feature_ids)
        await FeatureAssignmentService._validate_override_media(
            session, [item.override_media_id for item in assignments]
        )
        if any(item.source != "manual" for item in assignments):
            raise HTTPException(
                status_code=400,
                detail="Derived-фичи применяются только через endpoint предложений",
            )

        await session.execute(
            delete(FeatureProductLink).where(
                FeatureProductLink.product_id == product_id,
                FeatureProductLink.source == "manual",
            )
        )
        now = datetime.now()
        for item in assignments:
            session.add(
                FeatureProductLink(
                    product_id=product_id,
                    created_at=now,
                    updated_at=now,
                    **item.model_dump(),
                )
            )
        await CatalogRevisionService.bump_commit_and_purge(
            session,
            scope="product_features_update",
            product_ids=[product_id],
        )
        return await FeatureAssignmentService.get_product_workspace(session, product_id)

    @staticmethod
    async def delete_product_assignment(
        session: AsyncSession,
        product_id: int,
        feature_id: int,
    ) -> ManagerProductFeatureWorkspaceResponse:
        if await session.get(Product, product_id) is None:
            raise HTTPException(status_code=404, detail="Товар не найден")
        await session.execute(
            delete(FeatureProductLink).where(
                FeatureProductLink.product_id == product_id,
                FeatureProductLink.feature_id == feature_id,
            )
        )
        await CatalogRevisionService.bump_commit_and_purge(
            session,
            scope="product_feature_delete",
            product_ids=[product_id],
        )
        return await FeatureAssignmentService.get_product_workspace(session, product_id)

    @staticmethod
    async def apply_product_suggestions(
        session: AsyncSession,
        product_id: int,
        feature_ids: list[int],
    ) -> ManagerProductFeatureWorkspaceResponse:
        product = await session.get(Product, product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="Товар не найден")
        current = await FeatureResolverService.resolve_for_products(
            session, [product], include_suggestions=True
        )
        allowed = {
            item.id for item in current[int(product.id)]["automatic_suggestions"]
        }
        allowed.update(
            item.id
            for item in current[int(product.id)]["effective"]
            if item.source == "derived"
        )
        requested = set(feature_ids)
        invalid = sorted(requested - allowed)
        if invalid:
            raise HTTPException(
                status_code=409,
                detail={"message": "Предложения устарели; обновите preview", "feature_ids": invalid},
            )

        existing = {
            int(link.feature_id): link
            for link in (
                await session.execute(
                    select(FeatureProductLink).where(
                        FeatureProductLink.product_id == product_id,
                        FeatureProductLink.feature_id.in_(requested),
                    )
                )
            ).scalars().all()
        }
        now = datetime.now()
        for feature_id in requested:
            link = existing.get(feature_id)
            if link is None:
                link = FeatureProductLink(
                    product_id=product_id,
                    feature_id=feature_id,
                    source="derived",
                )
            link.source = "derived"
            link.is_enabled = True
            link.updated_at = now
            session.add(link)
        await CatalogRevisionService.bump_commit_and_purge(
            session,
            scope="product_feature_suggestions_apply",
            product_ids=[product_id],
        )
        return await FeatureAssignmentService.get_product_workspace(session, product_id)

    @staticmethod
    async def upsert_target_link(
        session: AsyncSession,
        *,
        feature_id: int,
        target_type: str,
        target_id: int,
        payload: FeatureTargetLinkPayload,
    ) -> None:
        await FeatureAssignmentService._validate_features(session, [feature_id])
        await FeatureAssignmentService._validate_override_media(session, [payload.override_media_id])
        config = {
            "brand": (Brand, FeatureBrandLink, FeatureBrandLink.brand_id, "brand_id"),
            "series": (ProductSeries, FeatureSeriesLink, FeatureSeriesLink.series_id, "series_id"),
        }.get(target_type)
        if config is None:
            raise ValueError("Unsupported feature target")
        target_model, link_model, target_column, target_field = config
        if await session.get(target_model, target_id) is None:
            raise HTTPException(status_code=404, detail="Цель назначения не найдена")
        link = (
            await session.execute(
                select(link_model).where(
                    target_column == target_id,
                    link_model.feature_id == feature_id,
                )
            )
        ).scalar_one_or_none()
        if link is None:
            link = link_model(**{target_field: target_id, "feature_id": feature_id})
        for key, value in payload.model_dump().items():
            setattr(link, key, value)
        link.source = "manual"
        link.updated_at = datetime.now()
        session.add(link)
        await CatalogRevisionService.bump_commit_and_purge(
            session,
            scope=f"feature_{target_type}_link_update",
        )

    @staticmethod
    async def delete_target_link(
        session: AsyncSession,
        *,
        feature_id: int,
        target_type: str,
        target_id: int,
    ) -> None:
        config = {
            "brand": (FeatureBrandLink, FeatureBrandLink.brand_id),
            "series": (FeatureSeriesLink, FeatureSeriesLink.series_id),
        }.get(target_type)
        if config is None:
            raise ValueError("Unsupported feature target")
        model, target_column = config
        await session.execute(
            delete(model).where(
                target_column == target_id,
                model.feature_id == feature_id,
            )
        )
        await CatalogRevisionService.bump_commit_and_purge(
            session,
            scope=f"feature_{target_type}_link_delete",
        )

    @staticmethod
    async def _validate_features(session: AsyncSession, feature_ids: list[int]) -> None:
        if not feature_ids:
            return
        found = set(
            (
                await session.execute(
                    select(Feature.id).where(
                        Feature.id.in_(set(feature_ids)),
                        Feature.is_active.is_(True),
                    )
                )
            ).scalars().all()
        )
        missing = sorted(set(feature_ids) - found)
        if missing:
            raise HTTPException(status_code=400, detail={"message": "Фичи не найдены", "feature_ids": missing})

    @staticmethod
    async def _validate_override_media(session: AsyncSession, media_ids) -> None:
        ids = {int(item) for item in media_ids if item is not None}
        if not ids:
            return
        found = set(
            (await session.execute(select(MediaAsset.id).where(MediaAsset.id.in_(ids)))).scalars().all()
        )
        missing = sorted(ids - found)
        if missing:
            raise HTTPException(status_code=400, detail={"message": "Media assets не найдены", "media_ids": missing})
