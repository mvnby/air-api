"""Series edits preserve existing media without admitting new legacy URLs."""

from copy import deepcopy

import pytest
from sqlalchemy import select

from core.config import settings
from models import Brand, IntegrationOutboxEvent, ProductSeries
from services.catalog_revision_service import CatalogRevisionService


CANONICAL = [f"https://cdn.mvn.by/library/original/{index:064x}.webp" for index in range(1, 7)]
LEGACY_GALLERY = "/media/products/shared/e79e270acf68213e0e492f3c9008da8333778e58dd730f184022e992747e93b6.webp"
LEGACY_HERO = "https://old-vendor.example/hero.webp"
LEGACY_FEATURE = "https://old-vendor.example/feature.webp"
LEGACY_ICON = "https://old-vendor.example/feature-icon.svg"
LEGACY_CONTENT = "https://old-vendor.example/content.webp"
NEW_EXTERNAL = "https://new-vendor.example/unmanaged.webp"
MEDIA_FIELDS = ("hero_image", "gallery_images", "feature_blocks", "content_blocks")


@pytest.fixture
async def legacy_series(async_client, db, monkeypatch):
    monkeypatch.setenv("MEDIA_STORAGE_PROVIDER", "r2")
    monkeypatch.setenv("PRODUCT_MEDIA_ORIGINAL_SOURCE_PROVIDER", "r2")
    brand = Brand(title="Kinhome", slug="kinhome")
    db.add(brand)
    await db.flush()
    series = ProductSeries(
        brand_id=brand.id,
        title="COSMO NORDIC",
        slug="cosmo-nordic",
        hero_image=LEGACY_HERO,
        gallery_images=[*CANONICAL, LEGACY_GALLERY],
        feature_blocks=[{
            "title": "Existing feature", "text": "Existing text",
            "image_url": LEGACY_FEATURE, "icon": LEGACY_ICON, "footnote": None,
        }],
        content_blocks=[{
            "kind": "image_text", "title": "Existing content", "text": "Description",
            "image_url": LEGACY_CONTENT, "layout": "text_left",
        }],
    )
    db.add(series)
    await db.commit()
    response = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    path = f"/api/manager/brands/{brand.id}/series/{series.id}"
    payload = {field: deepcopy(getattr(series, field)) for field in MEDIA_FIELDS}
    return path, headers, payload


async def catalog_state(db):
    revision = await CatalogRevisionService.get_current(db)
    event_ids = set((await db.execute(select(IntegrationOutboxEvent.event_id))).scalars())
    return revision, event_ids


@pytest.mark.asyncio
async def test_series_full_form_roundtrip_preserves_seventh_legacy_url_and_revision(
    async_client, db, legacy_series,
):
    path, headers, payload = legacy_series
    before = await catalog_state(db)
    response = await async_client.put(path, headers=headers, json=payload)
    assert response.status_code == 200, response.text
    assert {field: response.json()[field] for field in MEDIA_FIELDS} == payload
    assert await catalog_state(db) == before


@pytest.mark.asyncio
async def test_series_text_edits_and_gallery_reordering_retain_existing_media(
    async_client, db, legacy_series,
):
    path, headers, payload = legacy_series
    payload["short_description"] = "Обновлённое описание серии"
    payload["gallery_images"] = [LEGACY_GALLERY, *CANONICAL[1:]]
    payload["feature_blocks"][0]["text"] = "Updated feature explanation"
    payload["content_blocks"][0]["layout"] = "text_right"
    before, before_events = await catalog_state(db)
    response = await async_client.put(path, headers=headers, json=payload)
    assert response.status_code == 200, response.text
    assert all(response.json()[field] == value for field, value in payload.items())
    after, after_events = await catalog_state(db)
    assert after["revision"] == before["revision"] + 1
    assert len(after_events - before_events) == 1
    assert (await async_client.put(path, headers=headers, json=payload)).status_code == 200
    assert await catalog_state(db) == (after, after_events)


@pytest.mark.parametrize("field", ["hero", "gallery", "feature_image", "feature_icon", "content_image"])
@pytest.mark.asyncio
async def test_series_rejects_new_unmanaged_media_and_keeps_old_state(
    async_client, db, legacy_series, field,
):
    path, headers, original = legacy_series
    payload = deepcopy(original)
    if field == "hero":
        payload["hero_image"] = NEW_EXTERNAL
    elif field == "gallery":
        payload["gallery_images"].append(NEW_EXTERNAL)
    elif field.startswith("feature_"):
        payload["feature_blocks"][0]["image_url" if field == "feature_image" else "icon"] = NEW_EXTERNAL
    else:
        payload["content_blocks"][0]["image_url"] = NEW_EXTERNAL
    payload["title"] = "Must not be persisted"
    before = await catalog_state(db)
    await db.commit()
    response = await async_client.put(path, headers=headers, json=payload)
    assert response.status_code == 400, response.text
    assert "загрузить в медиатеку" in response.json()["detail"]
    # The test client shares one session across requests. Production closes the
    # failed request session, rolling back its uncommitted assignments.
    await db.rollback()
    listed = await async_client.get(path.rsplit("/", 1)[0], headers=headers)
    assert listed.status_code == 200
    unchanged = listed.json()["items"][0]
    assert unchanged["title"] == "COSMO NORDIC"
    assert {name: unchanged[name] for name in MEDIA_FIELDS} == original
    assert await catalog_state(db) == before


@pytest.mark.parametrize(
    "payload",
    [
        {"hero_image": LEGACY_GALLERY},
        {"gallery_images": [LEGACY_HERO]},
        {"feature_blocks": [{"title": "Copied", "image_url": LEGACY_CONTENT}]},
        {"feature_blocks": [{"title": "Copied", "icon": LEGACY_FEATURE}]},
        {"content_blocks": [{"title": "Copied", "image_url": LEGACY_FEATURE}]},
    ],
)
@pytest.mark.asyncio
async def test_series_does_not_copy_grandfathered_media_between_fields(
    async_client, legacy_series, payload,
):
    path, headers, _ = legacy_series
    response = await async_client.put(path, headers=headers, json=payload)
    assert response.status_code == 400, response.text


@pytest.mark.asyncio
async def test_other_series_and_creation_cannot_reuse_existing_legacy_media(
    async_client, legacy_series,
):
    path, headers, payload = legacy_series
    collection = path.rsplit("/", 1)[0]
    response = await async_client.post(
        collection, headers=headers, json={"title": "Other series", "slug": "other"},
    )
    assert response.status_code == 200, response.text
    other_id = response.json()["id"]
    update = await async_client.put(
        f"{collection}/{other_id}", headers=headers, json=payload,
    )
    assert update.status_code == 400, update.text
    create = await async_client.post(
        collection, headers=headers, json={"title": "New series", **payload},
    )
    assert create.status_code == 400, create.text


@pytest.mark.asyncio
async def test_series_can_replace_or_remove_legacy_media_with_library_media(
    async_client, legacy_series,
):
    path, headers, payload = legacy_series
    payload.update({
        "hero_image": CANONICAL[0],
        "gallery_images": CANONICAL,
        "feature_blocks": [{"title": "Managed feature", "image_url": CANONICAL[1], "icon": "wifi"}],
        "content_blocks": [],
    })
    response = await async_client.put(path, headers=headers, json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["hero_image"] == CANONICAL[0]
    assert response.json()["gallery_images"] == CANONICAL
    assert response.json()["feature_blocks"][0]["image_url"] == CANONICAL[1]
    assert response.json()["content_blocks"] == []
    # Once removed, a legacy URL is a new assignment and is rejected.
    rejected = await async_client.put(
        path, headers=headers, json={"gallery_images": [*CANONICAL, LEGACY_GALLERY]},
    )
    assert rejected.status_code == 400, rejected.text


@pytest.mark.asyncio
async def test_gallery_copy_to_products_still_rejects_preserved_legacy_media(
    async_client, legacy_series,
):
    path, headers, payload = legacy_series
    response = await async_client.post(
        f"{path}/gallery/apply-to-products",
        headers=headers,
        json={"source_urls": payload["gallery_images"]},
    )
    assert response.status_code == 400, response.text
    assert "series.gallery_images[7]" in response.json()["detail"]
