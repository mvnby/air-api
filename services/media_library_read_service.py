from __future__ import annotations

import math
from collections.abc import Iterable

from sqlalchemy import cast, exists, func, or_, union_all
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    Article,
    Brand,
    MediaAsset,
    Product,
    ProductAttachment,
    ProductImage,
    ProductImageVariant,
    ProductSeries,
    Service,
)


class MediaLibraryReadService:
    @staticmethod
    async def list_assets(
        session: AsyncSession,
        *,
        page: int,
        limit: int,
        query: str | None,
        kind: str | None,
        tag: str | None,
        status: str | None,
    ) -> dict:
        safe_page = max(1, int(page or 1))
        safe_limit = max(1, min(int(limit or 40), 100))
        conditions = []
        normalized_query = (query or "").strip()
        if normalized_query:
            pattern = f"%{normalized_query}%"
            conditions.append(
                or_(
                    MediaAsset.title.ilike(pattern),
                    MediaAsset.alt_text.ilike(pattern),
                    MediaAsset.description.ilike(pattern),
                    MediaAsset.source_filename.ilike(pattern),
                )
            )
        if kind:
            conditions.append(MediaAsset.kind == kind)
        if tag:
            conditions.append(
                MediaLibraryReadService.tag_filter_condition(session, tag)
            )
        if status:
            conditions.append(MediaAsset.processing_status == status)

        total = int(
            await session.scalar(
                select(func.count()).select_from(MediaAsset).where(*conditions)
            )
            or 0
        )
        page_rows = (
            await session.execute(
                select(MediaAsset)
                .where(*conditions)
                .order_by(MediaAsset.created_at.desc(), MediaAsset.id.desc())
                .offset((safe_page - 1) * safe_limit)
                .limit(safe_limit)
            )
        ).scalars().all()
        usage_counts = await MediaLibraryReadService.usage_counts_for_urls(
            session,
            [asset.url for asset in page_rows],
        )
        return {
            "items": [
                MediaLibraryReadService.serialize_asset(
                    asset,
                    usage_count=usage_counts.get(asset.url, 0),
                )
                for asset in page_rows
            ],
            "meta": {
                "total": total,
                "page": safe_page,
                "limit": safe_limit,
                "pages": math.ceil(total / safe_limit) if total else 1,
            },
        }

    @staticmethod
    def serialize_asset(asset: MediaAsset, *, usage_count: int) -> dict:
        return {
            "id": asset.id,
            "parent_asset_id": asset.parent_asset_id,
            "title": asset.title,
            "alt_text": asset.alt_text,
            "description": asset.description,
            "kind": asset.kind,
            "tags": asset.tags or [],
            "variant_type": asset.variant_type,
            "url": asset.url,
            "original_url": asset.original_url,
            "source_filename": asset.source_filename,
            "mime_type": asset.mime_type,
            "storage_provider": asset.storage_provider,
            "processing_status": asset.processing_status,
            "processing_error": asset.processing_error,
            "content_hash": asset.content_hash,
            "width": asset.width,
            "height": asset.height,
            "size_bytes": asset.size_bytes,
            "usage_count": int(usage_count),
            "created_by": asset.created_by,
            "created_at": asset.created_at,
            "updated_at": asset.updated_at,
        }

    @staticmethod
    def tag_filter_condition(session: AsyncSession, tag: str):
        dialect_name = session.get_bind().dialect.name
        if dialect_name == "postgresql":
            return cast(MediaAsset.tags, JSONB).contains([tag])
        if dialect_name == "sqlite":
            tag_values = (
                func.json_each(MediaAsset.tags)
                .table_valued("key", "value")
                .alias("media_asset_tag")
            )
            return (
                exists(
                    select(1)
                    .select_from(tag_values)
                    .where(tag_values.c.value == tag)
                )
                .correlate(MediaAsset)
            )
        return MediaAsset.tags.contains([tag])

    @staticmethod
    async def usage_counts_for_urls(
        session: AsyncSession,
        urls: Iterable[str],
    ) -> dict[str, int]:
        unique_urls = list(dict.fromkeys(str(url) for url in urls if url))
        counts = {url: 0 for url in unique_urls}
        if not unique_urls:
            return counts

        reference_rows = union_all(
            select(Product.main_image.label("url")).where(
                Product.main_image.in_(unique_urls)
            ),
            select(ProductImage.url.label("url")).where(
                ProductImage.url.in_(unique_urls)
            ),
            select(ProductImageVariant.url.label("url")).where(
                ProductImageVariant.url.in_(unique_urls)
            ),
            select(Article.main_image.label("url")).where(
                Article.main_image.in_(unique_urls)
            ),
            select(Article.cover_image.label("url")).where(
                Article.cover_image.in_(unique_urls),
                or_(
                    Article.main_image.is_(None),
                    Article.main_image != Article.cover_image,
                ),
            ),
            select(Brand.logo_url.label("url")).where(
                Brand.logo_url.in_(unique_urls)
            ),
            select(ProductSeries.hero_image.label("url")).where(
                ProductSeries.hero_image.in_(unique_urls)
            ),
            select(ProductAttachment.url.label("url")).where(
                ProductAttachment.url.in_(unique_urls)
            ),
            select(Service.image.label("url")).where(
                Service.image.in_(unique_urls)
            ),
        ).subquery("media_usage_reference")
        grouped_references = await session.execute(
            select(reference_rows.c.url, func.count())
            .where(reference_rows.c.url.is_not(None))
            .group_by(reference_rows.c.url)
        )
        for url, usage_count in grouped_references:
            counts[str(url)] = int(usage_count or 0)

        series_rows = await session.execute(
            select(ProductSeries.gallery_images, ProductSeries.feature_blocks).where(
                MediaLibraryReadService._series_json_reference_condition(
                    session,
                    unique_urls,
                )
            )
        )
        target_urls = set(unique_urls)
        for gallery_images, feature_blocks in series_rows:
            for image_url in gallery_images or []:
                if image_url in target_urls:
                    counts[image_url] += 1
            for block in feature_blocks or []:
                if not isinstance(block, dict):
                    continue
                image_url = block.get("image_url")
                if image_url in target_urls:
                    counts[image_url] += 1
        return counts

    @staticmethod
    def _series_json_reference_condition(
        session: AsyncSession,
        urls: list[str],
    ):
        dialect_name = session.get_bind().dialect.name
        if dialect_name == "postgresql":
            gallery_values = (
                func.jsonb_array_elements_text(cast(ProductSeries.gallery_images, JSONB))
                .table_valued("value")
                .alias("series_gallery_value")
            )
            feature_values = (
                func.jsonb_array_elements(cast(ProductSeries.feature_blocks, JSONB))
                .table_valued("value")
                .alias("series_feature_value")
            )
            gallery_match = exists(
                select(1)
                .select_from(gallery_values)
                .where(gallery_values.c.value.in_(urls))
            ).correlate(ProductSeries)
            feature_match = exists(
                select(1)
                .select_from(feature_values)
                .where(feature_values.c.value.op("->>")("image_url").in_(urls))
            ).correlate(ProductSeries)
            return or_(gallery_match, feature_match)

        if dialect_name == "sqlite":
            gallery_values = (
                func.json_each(ProductSeries.gallery_images)
                .table_valued("key", "value")
                .alias("series_gallery_value")
            )
            feature_values = (
                func.json_each(ProductSeries.feature_blocks)
                .table_valued("key", "value")
                .alias("series_feature_value")
            )
            gallery_match = exists(
                select(1)
                .select_from(gallery_values)
                .where(gallery_values.c.value.in_(urls))
            ).correlate(ProductSeries)
            feature_match = exists(
                select(1)
                .select_from(feature_values)
                .where(
                    func.json_extract(feature_values.c.value, "$.image_url").in_(urls)
                )
            ).correlate(ProductSeries)
            return or_(gallery_match, feature_match)

        raise RuntimeError(
            f"Unsupported database dialect for media usage batching: {dialect_name}"
        )
