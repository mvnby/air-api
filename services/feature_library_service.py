from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException
from slugify import slugify
from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import delete, select

from models import (
    Brand,
    Feature,
    FeatureBrandLink,
    FeatureCategory,
    FeatureProductLink,
    FeatureRule,
    FeatureSeriesLink,
    MediaAsset,
    Product,
)
from schemas_features import (
    FeatureCategoryResponse,
    FeatureCreatePayload,
    FeatureRuleResponse,
    FeatureUpdatePayload,
    ManagerFeatureResponse,
)
from services.catalog_revision_service import CatalogRevisionService
from services.feature_scope_policy import FeatureScopePolicy


class FeatureLibraryService:
    @staticmethod
    async def list_categories(session: AsyncSession) -> list[FeatureCategoryResponse]:
        rows = list(
            (
                await session.execute(
                    select(FeatureCategory).order_by(FeatureCategory.sort_order, FeatureCategory.name)
                )
            ).scalars().all()
        )
        return [FeatureCategoryResponse.model_validate(item, from_attributes=True) for item in rows]

    @staticmethod
    async def list_features(
        session: AsyncSession,
        *,
        search: str | None = None,
        category_id: int | None = None,
        brand_id: int | None = None,
        product_id: int | None = None,
        scope_type: str | None = None,
        is_active: bool | None = True,
    ) -> list[ManagerFeatureResponse]:
        stmt = select(Feature).options(selectinload(Feature.category), selectinload(Feature.rules))
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(or_(Feature.name.ilike(pattern), Feature.slug.ilike(pattern)))
        if category_id is not None:
            stmt = stmt.where(Feature.category_id == category_id)
        if brand_id is not None:
            linked = select(FeatureBrandLink.feature_id).where(FeatureBrandLink.brand_id == brand_id)
            stmt = stmt.where(or_(Feature.brand_id == brand_id, Feature.id.in_(linked)))
        if scope_type:
            stmt = stmt.where(Feature.scope_type == scope_type)
        if is_active is not None:
            stmt = stmt.where(Feature.is_active == is_active)
        stmt = stmt.order_by(Feature.sort_order, Feature.name, Feature.id)
        features = list((await session.execute(stmt)).scalars().all())
        if product_id is not None:
            product = await session.get(Product, product_id)
            if product is None:
                raise HTTPException(status_code=404, detail="Товар не найден")
            product_feature_ids = set(
                (
                    await session.execute(
                        select(FeatureProductLink.feature_id).where(
                            FeatureProductLink.product_id == product_id
                        )
                    )
                ).scalars().all()
            )
            series_feature_ids: set[int] = set()
            if product.series_id is not None:
                series_feature_ids = set(
                    (
                        await session.execute(
                            select(FeatureSeriesLink.feature_id).where(
                                FeatureSeriesLink.series_id == product.series_id
                            )
                        )
                    ).scalars().all()
                )
            features = [
                feature
                for feature in features
                if FeatureScopePolicy.allows_product(
                    feature,
                    product,
                    has_series_link=int(feature.id) in series_feature_ids,
                    has_product_link=int(feature.id) in product_feature_ids,
                    mode="manual",
                )
            ]
        return await FeatureLibraryService._serialize_many(session, features)

    @staticmethod
    async def get_feature(session: AsyncSession, feature_id: int) -> ManagerFeatureResponse:
        feature = await FeatureLibraryService._get_model(session, feature_id)
        return (await FeatureLibraryService._serialize_many(session, [feature]))[0]

    @staticmethod
    async def create_feature(session: AsyncSession, payload: FeatureCreatePayload) -> ManagerFeatureResponse:
        data = payload.model_dump(exclude={"rules"})
        data["slug"] = await FeatureLibraryService._unique_slug(session, data.get("slug"), payload.name)
        data["aliases"] = FeatureLibraryService._strings(data.get("aliases"))
        await FeatureLibraryService._validate_references(session, data)
        feature = Feature(**data)
        session.add(feature)
        await session.flush()
        await FeatureLibraryService._sync_rules(session, feature, payload.rules)
        if feature.scope_type == "brand" and feature.brand_id is not None:
            session.add(
                FeatureBrandLink(
                    brand_id=feature.brand_id,
                    feature_id=int(feature.id),
                    source="manual",
                    sort_order=feature.sort_order,
                )
            )
        await CatalogRevisionService.stage_invalidation(
            session,
            reason="feature_create",
        )
        await session.commit()
        return await FeatureLibraryService.get_feature(session, int(feature.id))

    @staticmethod
    async def update_feature(
        session: AsyncSession,
        feature_id: int,
        payload: FeatureUpdatePayload,
    ) -> ManagerFeatureResponse:
        feature = await FeatureLibraryService._get_model(session, feature_id)
        previous_scope_type = feature.scope_type
        previous_brand_id = feature.brand_id
        fields = payload.model_fields_set
        data = payload.model_dump(exclude_unset=True, exclude={"rules"})
        if "scope_type" in data and data["scope_type"] != "brand" and "brand_id" not in data:
            data["brand_id"] = None
        if "slug" in data:
            data["slug"] = await FeatureLibraryService._unique_slug(
                session, data.get("slug"), data.get("name") or feature.name, exclude_id=feature_id
            )
        if "aliases" in data:
            data["aliases"] = FeatureLibraryService._strings(data["aliases"])
        await FeatureLibraryService._validate_references(session, {**feature.__dict__, **data})
        for key, value in data.items():
            setattr(feature, key, value)
        feature.updated_at = datetime.now()
        session.add(feature)
        if "rules" in fields:
            await FeatureLibraryService._sync_rules(session, feature, payload.rules or [])
        await FeatureLibraryService._sync_owner_brand_link(
            session,
            feature,
            previous_scope_type=previous_scope_type,
            previous_brand_id=previous_brand_id,
        )
        await CatalogRevisionService.stage_invalidation(
            session,
            reason="feature_update",
        )
        await session.commit()
        return await FeatureLibraryService.get_feature(session, feature_id)

    @staticmethod
    async def archive_feature(session: AsyncSession, feature_id: int) -> ManagerFeatureResponse:
        feature = await FeatureLibraryService._get_model(session, feature_id)
        feature.is_active = False
        feature.archived_at = datetime.now()
        feature.updated_at = datetime.now()
        session.add(feature)
        await CatalogRevisionService.stage_invalidation(
            session,
            reason="feature_archive",
        )
        await session.commit()
        return await FeatureLibraryService.get_feature(session, feature_id)

    @staticmethod
    async def _get_model(session: AsyncSession, feature_id: int) -> Feature:
        feature = (
            await session.execute(
                select(Feature)
                .where(Feature.id == feature_id)
                .options(selectinload(Feature.category), selectinload(Feature.rules))
            )
        ).scalar_one_or_none()
        if feature is None:
            raise HTTPException(status_code=404, detail="Фича не найдена")
        return feature

    @staticmethod
    async def _validate_references(session: AsyncSession, data: dict[str, Any]) -> None:
        category_id = data.get("category_id")
        if category_id is None or await session.get(FeatureCategory, category_id) is None:
            raise HTTPException(status_code=400, detail="Категория фичи не найдена")
        brand_id = data.get("brand_id")
        if data.get("scope_type") == "brand" and brand_id is None:
            raise HTTPException(status_code=400, detail="Для брендовой фичи нужен brand_id")
        if brand_id is not None and await session.get(Brand, brand_id) is None:
            raise HTTPException(status_code=400, detail="Бренд не найден")
        for key in ("icon_media_id", "image_media_id"):
            media_id = data.get(key)
            if media_id is not None and await session.get(MediaAsset, media_id) is None:
                raise HTTPException(status_code=400, detail=f"Media asset #{media_id} не найден")

    @staticmethod
    async def _unique_slug(
        session: AsyncSession,
        requested: str | None,
        name: str,
        *,
        exclude_id: int | None = None,
    ) -> str:
        base = slugify((requested or name).strip(), lowercase=True) or "feature"
        candidate, suffix = base, 2
        while True:
            stmt = select(Feature.id).where(Feature.slug == candidate)
            if exclude_id is not None:
                stmt = stmt.where(Feature.id != exclude_id)
            if (await session.execute(stmt)).scalar_one_or_none() is None:
                return candidate
            candidate, suffix = f"{base}-{suffix}", suffix + 1

    @staticmethod
    async def _sync_rules(session: AsyncSession, feature: Feature, rules) -> None:
        await session.execute(delete(FeatureRule).where(FeatureRule.feature_id == feature.id))
        for index, payload in enumerate(rules):
            data = payload.model_dump()
            if not data.get("sort_order"):
                data["sort_order"] = index * 10
            session.add(FeatureRule(feature_id=int(feature.id), **data))
        await session.flush()

    @staticmethod
    async def _sync_owner_brand_link(
        session: AsyncSession,
        feature: Feature,
        *,
        previous_scope_type: str,
        previous_brand_id: int | None,
    ) -> None:
        owner_changed = (
            previous_scope_type != feature.scope_type
            or previous_brand_id != feature.brand_id
        )
        if not owner_changed:
            return
        if previous_scope_type == "brand" and previous_brand_id is not None:
            await session.execute(
                delete(FeatureBrandLink).where(
                    FeatureBrandLink.feature_id == feature.id,
                    FeatureBrandLink.brand_id == previous_brand_id,
                )
            )
        if feature.scope_type != "brand" or feature.brand_id is None:
            return
        existing = (
            await session.execute(
                select(FeatureBrandLink).where(
                    FeatureBrandLink.feature_id == feature.id,
                    FeatureBrandLink.brand_id == feature.brand_id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                FeatureBrandLink(
                    feature_id=int(feature.id),
                    brand_id=feature.brand_id,
                    source="manual",
                    sort_order=feature.sort_order,
                )
            )

    @staticmethod
    async def _serialize_many(session: AsyncSession, features: list[Feature]) -> list[ManagerFeatureResponse]:
        if not features:
            return []
        ids = [int(feature.id) for feature in features]
        counts = {}
        for model, label in (
            (FeatureBrandLink, "brands_count"),
            (FeatureSeriesLink, "series_count"),
            (FeatureProductLink, "products_count"),
        ):
            rows = list(
                (
                    await session.execute(
                        select(model.feature_id, func.count(model.id))
                        .where(model.feature_id.in_(ids), model.is_enabled.is_(True))
                        .group_by(model.feature_id)
                    )
                ).all()
            )
            for feature_id, count in rows:
                counts.setdefault(int(feature_id), {})[label] = int(count)

        media_ids = {
            int(value)
            for feature in features
            for value in (feature.icon_media_id, feature.image_media_id)
            if value is not None
        }
        media = {}
        if media_ids:
            rows = list((await session.execute(select(MediaAsset).where(MediaAsset.id.in_(media_ids)))).scalars().all())
            media = {int(item.id): item.url for item in rows if item.id is not None}

        payload = []
        for feature in features:
            category = feature.category
            payload.append(
                ManagerFeatureResponse(
                    id=int(feature.id),
                    slug=feature.slug,
                    name=feature.name,
                    short_description=feature.short_description,
                    full_description=feature.full_description,
                    category=FeatureCategoryResponse.model_validate(category, from_attributes=True),
                    scope_type=feature.scope_type,
                    brand_id=feature.brand_id,
                    icon_media_id=feature.icon_media_id,
                    image_media_id=feature.image_media_id,
                    icon=feature.icon,
                    icon_url=media.get(int(feature.icon_media_id)) if feature.icon_media_id else None,
                    image_url=(media.get(int(feature.image_media_id)) if feature.image_media_id else None) or feature.image_url,
                    video_url=feature.video_url,
                    footnote=feature.footnote,
                    source_url=feature.source_url,
                    aliases=FeatureLibraryService._strings(feature.aliases),
                    seo_title=feature.seo_title,
                    seo_description=feature.seo_description,
                    source_notes=feature.source_notes,
                    legal_notes=feature.legal_notes,
                    is_active=feature.is_active,
                    sort_order=feature.sort_order,
                    rules=[FeatureRuleResponse.model_validate(rule, from_attributes=True) for rule in feature.rules],
                    created_at=feature.created_at,
                    updated_at=feature.updated_at,
                    archived_at=feature.archived_at,
                    **counts.get(int(feature.id), {}),
                )
            )
        return payload

    @staticmethod
    def _strings(value) -> list[str]:
        result = []
        for item in value or []:
            text = str(item or "").strip()
            if text and text not in result:
                result.append(text)
        return result
