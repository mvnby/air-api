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
from services.catalog_invalidation_commit_service import (
    CatalogInvalidationCommitService,
)
from services.catalog_revision_service import CatalogRevisionService
from services.feature_resolver_service import FeatureResolverService
from services.feature_scope_policy import FeatureScopePolicy


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
        features = await FeatureAssignmentService._get_active_features(session, feature_ids)
        await FeatureAssignmentService._validate_override_media(
            session, [item.override_media_id for item in assignments]
        )
        if any(item.source != "manual" for item in assignments):
            raise HTTPException(
                status_code=400,
                detail="Derived-фичи применяются только через endpoint предложений",
            )

        existing_links = list(
            (
                await session.execute(
                    select(FeatureProductLink).where(
                        FeatureProductLink.product_id == product_id
                    )
                )
            ).scalars().all()
        )
        existing_by_feature_id = {
            int(link.feature_id): link for link in existing_links
        }
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
        for feature_id, feature in features.items():
            if not FeatureScopePolicy.allows_product(
                feature,
                product,
                has_series_link=feature_id in series_feature_ids,
                has_product_link=feature_id in existing_by_feature_id,
                mode="manual",
            ):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": "Фича неприменима к этому товару",
                        "feature_ids": [feature_id],
                    },
                )

        requested_ids = set(feature_ids)
        for link in existing_links:
            if link.source == "manual" and int(link.feature_id) not in requested_ids:
                await session.delete(link)

        now = datetime.now()
        for item in assignments:
            link = existing_by_feature_id.get(item.feature_id)
            if link is None:
                link = FeatureProductLink(
                    product_id=product_id,
                    feature_id=item.feature_id,
                    created_at=now,
                )
            for key, value in item.model_dump(exclude={"feature_id"}).items():
                setattr(link, key, value)
            link.source = "manual"
            link.updated_at = now
            session.add(link)
        await CatalogRevisionService.stage_invalidation(
            session,
            reason="product_features_update",
            product_ids=[product_id],
        )
        await session.commit()
        return await FeatureAssignmentService.get_product_workspace(session, product_id)

    @staticmethod
    async def delete_product_assignment(
        session: AsyncSession,
        product_id: int,
        feature_id: int,
    ) -> ManagerProductFeatureWorkspaceResponse:
        if await session.get(Product, product_id) is None:
            raise HTTPException(status_code=404, detail="Товар не найден")
        result = await session.execute(
            delete(FeatureProductLink).where(
                FeatureProductLink.product_id == product_id,
                FeatureProductLink.feature_id == feature_id,
            )
        )
        await CatalogInvalidationCommitService.commit_registered_global_mutation(
            session,
            producer="feature_assignment.delete_product_assignment",
            changed=result.rowcount != 0,
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
        suggestion_ids = {
            item.id for item in current[int(product.id)]["automatic_suggestions"]
        }
        allowed = suggestion_ids | {
            item.id
            for item in current[int(product.id)]["effective"]
            if item.source == "derived"
        }
        requested = set(feature_ids)
        invalid = sorted(requested - allowed)
        if invalid:
            raise HTTPException(
                status_code=409,
                detail={"message": "Предложения устарели; обновите preview", "feature_ids": invalid},
            )

        # Universal rules now resolve automatically and never need stored links.
        # Keep writes only for historical scope=derived suggestions while old
        # Manager builds and legacy rows are being phased out.
        legacy_ids = requested & suggestion_ids
        if legacy_ids:
            existing = {
                int(link.feature_id): link
                for link in (
                    await session.execute(
                        select(FeatureProductLink).where(
                            FeatureProductLink.product_id == product_id,
                            FeatureProductLink.feature_id.in_(legacy_ids),
                        )
                    )
                ).scalars().all()
            }
            now = datetime.now()
            for feature_id in legacy_ids:
                link = existing.get(feature_id) or FeatureProductLink(
                    product_id=product_id,
                    feature_id=feature_id,
                )
                link.source = "derived"
                link.is_enabled = True
                link.updated_at = now
                session.add(link)
            await CatalogRevisionService.stage_invalidation(
                session,
                reason="legacy_product_feature_suggestion_apply",
                product_ids=[product_id],
            )
        await session.commit()
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
        config = {
            "brand": (Brand, FeatureBrandLink, FeatureBrandLink.brand_id, "brand_id"),
            "series": (ProductSeries, FeatureSeriesLink, FeatureSeriesLink.series_id, "series_id"),
        }.get(target_type)
        if config is None:
            raise ValueError("Unsupported feature target")
        target_model, link_model, target_column, target_field = config
        if target_type == "series":
            target = (
                await session.execute(
                    select(ProductSeries)
                    .where(ProductSeries.id == target_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
        else:
            target = (
                await session.execute(
                    select(Brand)
                    .where(Brand.id == target_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
        if target is None:
            raise HTTPException(status_code=404, detail="Цель назначения не найдена")
        feature = (await FeatureAssignmentService._get_active_features(session, [feature_id]))[
            feature_id
        ]
        await FeatureAssignmentService._validate_override_media(session, [payload.override_media_id])
        target_brand_id = int(target.id) if target_type == "brand" else target.brand_id
        if not FeatureScopePolicy.allows_target(
            feature,
            target_type=target_type,
            brand_id=target_brand_id,
        ):
            raise HTTPException(
                status_code=400,
                detail="Фича неприменима к выбранному бренду или серии",
            )
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
        if target_type == "brand" and payload.is_featured:
            raise HTTPException(status_code=400, detail="Важность задаётся только для серии")
        if target_type == "series" and payload.is_featured:
            featured_count = (
                await session.execute(
                    select(FeatureSeriesLink.id).where(
                        FeatureSeriesLink.series_id == target_id,
                        FeatureSeriesLink.is_featured.is_(True),
                        FeatureSeriesLink.is_enabled.is_(True),
                        FeatureSeriesLink.feature_id != feature_id,
                    )
                )
            ).scalars().all()
            if len(featured_count) >= 3:
                raise HTTPException(status_code=400, detail="У серии может быть не более трёх главных фич")
        link_data = payload.model_dump()
        if target_type == "brand":
            link_data.pop("is_featured", None)
        for key, value in link_data.items():
            setattr(link, key, value)
        link.source = "manual"
        link.updated_at = datetime.now()
        session.add(link)
        await CatalogRevisionService.stage_invalidation(
            session,
            reason=f"feature_{target_type}_link_update",
        )
        await session.commit()

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
        if target_type == "series":
            locked_target = (
                await session.execute(
                    select(ProductSeries.id)
                    .where(ProductSeries.id == target_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if locked_target is None:
                raise HTTPException(status_code=404, detail="Цель назначения не найдена")
        else:
            await session.execute(
                select(Brand.id)
                .where(Brand.id == target_id)
                .with_for_update()
            )
        result = await session.execute(
            delete(model).where(
                target_column == target_id,
                model.feature_id == feature_id,
            )
        )
        await CatalogInvalidationCommitService.commit_registered_global_mutation(
            session,
            producer=f"feature_assignment.delete_target_link.{target_type}",
            changed=result.rowcount != 0,
        )

    @staticmethod
    async def _get_active_features(
        session: AsyncSession,
        feature_ids: list[int],
    ) -> dict[int, Feature]:
        if not feature_ids:
            return {}
        rows = list(
            (
                await session.execute(
                    select(Feature).where(
                        Feature.id.in_(set(feature_ids)),
                        Feature.is_active.is_(True),
                        Feature.archived_at.is_(None),
                    )
                )
            ).scalars().all()
        )
        found = {int(feature.id): feature for feature in rows}
        missing = sorted(set(feature_ids) - set(found))
        if missing:
            raise HTTPException(status_code=400, detail={"message": "Фичи не найдены", "feature_ids": missing})
        return found

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
