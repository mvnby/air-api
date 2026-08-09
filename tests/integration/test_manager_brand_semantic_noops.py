from datetime import datetime

import pytest
from sqlalchemy import select

from core.config import settings
from models import (
    Brand,
    Feature,
    FeatureBrandLink,
    FeatureSeriesLink,
    IntegrationOutboxEvent,
    ProductSeries,
    Tag,
    TagGroup,
)
from services.catalog_invalidation_contracts import (
    CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT,
)
from services.catalog_revision_service import CatalogRevisionService


async def _auth_headers(async_client):
    response = await async_client.post(
        "/login/access-token",
        data={
            "username": settings.ADMIN_USERNAME,
            "password": settings.ADMIN_PASSWORD,
        },
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _catalog_state(
    session,
) -> tuple[int, datetime, dict[str, str | None]]:
    revision = await CatalogRevisionService.get_current(session)
    events = (
        await session.execute(
            select(IntegrationOutboxEvent).where(
                IntegrationOutboxEvent.event_type
                == CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT
            )
        )
    ).scalars().all()
    return int(revision["revision"]), revision["updated_at"], {
        event.event_id: event.payload.get("reason") for event in events
    }


def _assert_single_catalog_change(
    before: tuple[int, datetime, dict[str, str | None]],
    after: tuple[int, datetime, dict[str, str | None]],
    *,
    reason: str,
) -> None:
    before_revision, before_updated_at, before_events = before
    after_revision, after_updated_at, after_events = after
    new_event_ids = set(after_events) - set(before_events)

    assert after_revision == before_revision + 1
    assert after_updated_at != before_updated_at
    assert len(after_events) == len(before_events) + 1
    assert len(new_event_ids) == 1
    assert after_events[new_event_ids.pop()] == reason


async def _stored_mutation_state(
    session,
    *,
    brand_id: int,
    feature_ids: list[int],
    series_id: int,
) -> dict:
    session.expire_all()
    brand = await session.get(Brand, brand_id)
    series = await session.get(ProductSeries, series_id)
    features = (
        await session.execute(
            select(Feature).where(Feature.id.in_(feature_ids)).order_by(Feature.id)
        )
    ).scalars().all()
    brand_tag = (
        await session.execute(
            select(Tag)
            .join(TagGroup, Tag.group_id == TagGroup.id)
            .where(TagGroup.slug == "brand", Tag.slug == brand.slug)
        )
    ).scalar_one()
    brand_links = (
        await session.execute(
            select(FeatureBrandLink)
            .where(FeatureBrandLink.feature_id.in_(feature_ids))
            .order_by(FeatureBrandLink.feature_id)
        )
    ).scalars().all()
    series_links = (
        await session.execute(
            select(FeatureSeriesLink)
            .where(FeatureSeriesLink.series_id == series_id)
            .order_by(FeatureSeriesLink.feature_id)
        )
    ).scalars().all()

    return {
        "brand": (
            brand.title,
            brand.slug,
            brand.logo_url,
            brand.short_description,
            brand.description,
            brand.is_published,
            brand.sort_order,
            brand.created_at,
        ),
        "series": (
            series.title,
            series.slug,
            series.tagline,
            series.short_description,
            series.description,
            series.hero_image,
            series.gallery_images,
            series.features,
            series.feature_blocks,
            series.content_blocks,
            series.footnotes,
            series.seo_title,
            series.seo_description,
            series.source_url,
            series.is_featured,
            series.is_published,
            series.sort_order,
            series.created_at,
        ),
        "features": [
            (
                feature.id,
                feature.name,
                feature.slug,
                feature.full_description,
                feature.image_url,
                feature.icon,
                feature.footnote,
                feature.source_url,
                feature.aliases,
                feature.is_active,
                feature.sort_order,
                feature.updated_at,
                feature.archived_at,
            )
            for feature in features
        ],
        "brand_tag": (
            brand_tag.id,
            brand_tag.group_id,
            brand_tag.title,
            brand_tag.slug,
            brand_tag.is_public,
            brand_tag.is_filter,
        ),
        "brand_links": [
            (
                link.id,
                link.brand_id,
                link.feature_id,
                link.sort_order,
                link.created_at,
                link.updated_at,
            )
            for link in brand_links
        ],
        "series_links": [
            (
                link.id,
                link.series_id,
                link.feature_id,
                link.sort_order,
                link.created_at,
                link.updated_at,
            )
            for link in series_links
        ],
    }


async def _create_brand_fixture(async_client, headers) -> dict[str, int]:
    brand_response = await async_client.post(
        "/api/manager/brands",
        headers=headers,
        json={
            "title": "Semantic Brand",
            "slug": "semantic-brand",
            "logo_url": "https://example.com/brand.webp",
            "short_description": "Short brand summary",
            "description": "Brand description",
            "is_published": True,
            "sort_order": 7,
        },
    )
    assert brand_response.status_code == 200, brand_response.text
    brand_id = int(brand_response.json()["id"])

    feature_payloads = [
        {
            "title": "Balanced Air",
            "slug": "balanced-air",
            "text": "Balanced airflow",
            "image_url": "/media/balanced.webp",
            "icon": "air",
            "footnote": "Model dependent",
            "source_url": "https://example.com/balanced",
            "aliases": ["quiet", "balanced"],
            "is_published": True,
            "sort_order": 4,
        },
        {
            "title": "Self Clean",
            "slug": "self-clean",
            "text": "Keeps the exchanger clean",
            "aliases": ["clean"],
            "is_published": True,
            "sort_order": 8,
        },
        {
            "title": "Archive Me",
            "slug": "archive-me",
            "text": "Unlinked feature",
            "is_published": True,
            "sort_order": 12,
        },
    ]
    feature_ids: list[int] = []
    for payload in feature_payloads:
        response = await async_client.post(
            f"/api/manager/brands/{brand_id}/features",
            headers=headers,
            json=payload,
        )
        assert response.status_code == 200, response.text
        feature_ids.append(int(response.json()["id"]))

    series_response = await async_client.post(
        f"/api/manager/brands/{brand_id}/series",
        headers=headers,
        json={
            "title": "Semantic Series",
            "slug": "semantic-series",
            "tagline": "Series tagline",
            "short_description": "Short description",
            "description": "Series description",
            "hero_image": "/media/hero.webp",
            "gallery_images": ["/media/one.webp", "/media/two.webp"],
            "features": ["Wi-Fi", "Quiet"],
            "feature_blocks": [
                {
                    "title": "Comfort",
                    "text": "Comfort text",
                    "image_url": "/media/comfort.webp",
                    "icon": "comfort",
                    "footnote": "Feature note",
                }
            ],
            "content_blocks": [
                {
                    "kind": "image_text",
                    "title": "Details",
                    "text": "Detailed text",
                    "image_url": "/media/details.webp",
                    "layout": "text_right",
                }
            ],
            "footnotes": ["Series note"],
            "seo_title": "Semantic series SEO",
            "seo_description": "Semantic series SEO description",
            "source_url": "https://example.com/series",
            "is_published": True,
            "sort_order": 9,
            "brand_feature_ids": feature_ids[:2],
        },
    )
    assert series_response.status_code == 200, series_response.text
    return {
        "brand_id": brand_id,
        "first_feature_id": feature_ids[0],
        "second_feature_id": feature_ids[1],
        "archivable_feature_id": feature_ids[2],
        "series_id": int(series_response.json()["id"]),
    }


@pytest.mark.asyncio
async def test_manager_brand_mutations_skip_semantic_noops(async_client, db):
    headers = await _auth_headers(async_client)
    ids = await _create_brand_fixture(async_client, headers)
    feature_ids = [
        ids["first_feature_id"],
        ids["second_feature_id"],
        ids["archivable_feature_id"],
    ]
    stored_before = await _stored_mutation_state(
        db,
        brand_id=ids["brand_id"],
        feature_ids=feature_ids,
        series_id=ids["series_id"],
    )
    catalog_before = await _catalog_state(db)

    empty_updates = [
        f"/api/manager/brands/{ids['brand_id']}",
        f"/api/manager/brands/{ids['brand_id']}/features/{ids['first_feature_id']}",
        f"/api/manager/brands/{ids['brand_id']}/series/{ids['series_id']}",
    ]
    for endpoint in empty_updates:
        response = await async_client.put(endpoint, headers=headers, json={})
        assert response.status_code == 200, response.text

    identical_brand = await async_client.put(
        f"/api/manager/brands/{ids['brand_id']}",
        headers=headers,
        json={
            "title": "  Semantic Brand  ",
            "slug": " semantic-brand ",
            "logo_url": " https://example.com/brand.webp ",
            "short_description": " Short brand summary ",
            "description": " Brand description ",
            "is_published": True,
            "sort_order": 7,
        },
    )
    assert identical_brand.status_code == 200, identical_brand.text

    identical_feature = await async_client.put(
        (
            f"/api/manager/brands/{ids['brand_id']}/features/"
            f"{ids['first_feature_id']}"
        ),
        headers=headers,
        json={
            "title": " Balanced Air ",
            "slug": " balanced-air ",
            "text": " Balanced airflow ",
            "image_url": " /media/balanced.webp ",
            "icon": " air ",
            "footnote": " Model dependent ",
            "source_url": " https://example.com/balanced ",
            "aliases": [" quiet ", "balanced", "quiet"],
            "is_published": True,
            "sort_order": 4,
        },
    )
    assert identical_feature.status_code == 200, identical_feature.text

    identical_series = await async_client.put(
        f"/api/manager/brands/{ids['brand_id']}/series/{ids['series_id']}",
        headers=headers,
        json={
            "title": " Semantic Series ",
            "slug": " semantic-series ",
            "tagline": " Series tagline ",
            "short_description": " Short description ",
            "description": " Series description ",
            "hero_image": " /media/hero.webp ",
            "gallery_images": [
                " /media/one.webp ",
                "/media/two.webp",
                "/media/one.webp",
            ],
            "features": [" Wi-Fi ", "Quiet", "Wi-Fi"],
            "feature_blocks": [
                {
                    "title": " Comfort ",
                    "text": " Comfort text ",
                    "image_url": " /media/comfort.webp ",
                    "icon": " comfort ",
                    "footnote": " Feature note ",
                }
            ],
            "content_blocks": [
                {
                    "kind": "image_text",
                    "title": " Details ",
                    "text": " Detailed text ",
                    "image_url": " /media/details.webp ",
                    "layout": "text_right",
                }
            ],
            "footnotes": [" Series note ", "Series note"],
            "seo_title": " Semantic series SEO ",
            "seo_description": " Semantic series SEO description ",
            "source_url": " https://example.com/series ",
            "is_featured": False,
            "is_published": True,
            "sort_order": 9,
            "brand_feature_ids": [
                ids["second_feature_id"],
                ids["first_feature_id"],
            ],
        },
    )
    assert identical_series.status_code == 200, identical_series.text

    stored_after = await _stored_mutation_state(
        db,
        brand_id=ids["brand_id"],
        feature_ids=feature_ids,
        series_id=ids["series_id"],
    )
    catalog_after = await _catalog_state(db)
    assert stored_after == stored_before
    assert catalog_after == catalog_before

    brand_before = catalog_after
    brand_update = await async_client.put(
        f"/api/manager/brands/{ids['brand_id']}",
        headers=headers,
        json={"title": "Semantic Brand Updated"},
    )
    assert brand_update.status_code == 200, brand_update.text
    brand_after = await _catalog_state(db)
    _assert_single_catalog_change(brand_before, brand_after, reason="brand_update")

    series_update = await async_client.put(
        f"/api/manager/brands/{ids['brand_id']}/series/{ids['series_id']}",
        headers=headers,
        json={"tagline": "Updated series tagline"},
    )
    assert series_update.status_code == 200, series_update.text
    series_after = await _catalog_state(db)
    _assert_single_catalog_change(
        brand_after,
        series_after,
        reason="brand_series_update",
    )

    feature_update = await async_client.put(
        (
            f"/api/manager/brands/{ids['brand_id']}/features/"
            f"{ids['first_feature_id']}"
        ),
        headers=headers,
        json={"footnote": "Updated feature note"},
    )
    assert feature_update.status_code == 200, feature_update.text
    feature_after = await _catalog_state(db)
    _assert_single_catalog_change(
        series_after,
        feature_after,
        reason="brand_feature_update",
    )

    changed_state = await _stored_mutation_state(
        db,
        brand_id=ids["brand_id"],
        feature_ids=feature_ids,
        series_id=ids["series_id"],
    )
    assert changed_state["brand"][0] == "Semantic Brand Updated"
    assert changed_state["brand_tag"][0] == stored_before["brand_tag"][0]
    assert changed_state["brand_tag"][2] == "Semantic Brand Updated"
    assert changed_state["series"][2] == "Updated series tagline"
    assert changed_state["features"][0][6] == "Updated feature note"
    assert changed_state["features"][0][11] != stored_before["features"][0][11]
    assert changed_state["brand_links"] == stored_before["brand_links"]
    assert changed_state["series_links"] == stored_before["series_links"]

    first_delete = await async_client.delete(
        (
            f"/api/manager/brands/{ids['brand_id']}/features/"
            f"{ids['archivable_feature_id']}"
        ),
        headers=headers,
    )
    assert first_delete.status_code == 200, first_delete.text
    first_delete_catalog = await _catalog_state(db)
    _assert_single_catalog_change(
        feature_after,
        first_delete_catalog,
        reason="brand_feature_delete",
    )
    db.expire_all()
    archived_after_first = await db.get(Feature, ids["archivable_feature_id"])
    first_archived_at = archived_after_first.archived_at
    first_updated_at = archived_after_first.updated_at
    assert archived_after_first.is_active is False
    assert first_archived_at is not None

    repeated_delete = await async_client.delete(
        (
            f"/api/manager/brands/{ids['brand_id']}/features/"
            f"{ids['archivable_feature_id']}"
        ),
        headers=headers,
    )
    assert repeated_delete.status_code == 200, repeated_delete.text
    repeated_delete_catalog = await _catalog_state(db)
    assert repeated_delete_catalog == first_delete_catalog
    db.expire_all()
    archived_after_second = await db.get(Feature, ids["archivable_feature_id"])
    assert archived_after_second.archived_at == first_archived_at
    assert archived_after_second.updated_at == first_updated_at
