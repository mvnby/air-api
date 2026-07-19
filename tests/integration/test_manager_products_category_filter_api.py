import pytest
from sqlmodel import select

from core.config import settings
from crud.supplier import ProductLocalStockDAO
from models import Brand, Product, ProductTagLink, Tag, TagGroup


async def _auth_headers(async_client):
    login_resp = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _get_or_create_category_tag(session, slug: str, title: str) -> Tag:
    group = (await session.execute(select(TagGroup).where(TagGroup.slug == "category"))).scalar_one_or_none()
    if group is None:
        group = TagGroup(
            title="Категория",
            slug="category",
            color="primary",
            is_public=True,
            allow_multiple=False,
        )
        session.add(group)
        await session.commit()
        await session.refresh(group)

    tag = (await session.execute(select(Tag).where(Tag.slug == slug))).scalar_one_or_none()
    if tag is None:
        tag = Tag(
            title=title,
            slug=slug,
            group_id=group.id,
            is_public=True,
            is_filter=True,
        )
        session.add(tag)
        await session.commit()
        await session.refresh(tag)
    return tag


@pytest.mark.asyncio
async def test_manager_products_list_respects_category_slug(async_client, db):
    headers = await _auth_headers(async_client)

    household_tag = await _get_or_create_category_tag(db, "cat-household", "Бытовые")
    multi_tag = await _get_or_create_category_tag(db, "cat-multi", "Мульти-сплит")
    industrial_tag = await _get_or_create_category_tag(db, "cat-industrial", "Полупром")

    marker = "UNITCAT123"
    p_house = Product(title=f"{marker} TCL Household", slug=f"{marker.lower()}-house", price=1000, specs={"area_m2": 20}, is_published=True)
    p_multi = Product(title=f"{marker} TCL Multi", slug=f"{marker.lower()}-multi", price=1100, specs={"area_m2": 20}, is_published=True)
    p_ind = Product(title=f"{marker} TCL Industrial", slug=f"{marker.lower()}-ind", price=1200, specs={"area_m2": 20}, is_published=True)
    db.add_all([p_house, p_multi, p_ind])
    await db.commit()
    for p in [p_house, p_multi, p_ind]:
        await db.refresh(p)

    db.add_all(
        [
            ProductTagLink(product_id=p_house.id, tag_id=household_tag.id),
            ProductTagLink(product_id=p_multi.id, tag_id=multi_tag.id),
            ProductTagLink(product_id=p_ind.id, tag_id=industrial_tag.id),
        ]
    )
    await db.commit()

    resp = await async_client.get(
        "/api/manager/products/list",
        headers=headers,
        params={"search": marker, "category_slug": "cat-multi", "limit": 100},
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    ids = {item["id"] for item in items}
    assert p_multi.id in ids
    assert p_house.id not in ids
    assert p_ind.id not in ids


@pytest.mark.asyncio
async def test_manager_products_list_can_show_missing_category_products(async_client, db):
    headers = await _auth_headers(async_client)

    household_tag = await _get_or_create_category_tag(db, "cat-household", "Бытовые")
    multi_tag = await _get_or_create_category_tag(db, "cat-multi", "Мульти-сплит")
    industrial_tag = await _get_or_create_category_tag(db, "cat-industrial", "Полупром")

    marker = "UNITCATMISS111"
    missing = Product(
        title=f"{marker} Missing Category",
        slug=f"{marker.lower()}-missing",
        price=1000,
        specs={"area_m2": 20},
        is_published=True,
    )
    household = Product(
        title=f"{marker} Household",
        slug=f"{marker.lower()}-household",
        price=1100,
        specs={"area_m2": 20},
        is_published=True,
    )
    multi = Product(
        title=f"{marker} Multi",
        slug=f"{marker.lower()}-multi",
        price=1200,
        specs={"area_m2": 20},
        is_published=True,
    )
    industrial = Product(
        title=f"{marker} Industrial",
        slug=f"{marker.lower()}-industrial",
        price=1300,
        specs={"area_m2": 20},
        is_published=True,
    )
    db.add_all([missing, household, multi, industrial])
    await db.commit()
    for product in [missing, household, multi, industrial]:
        await db.refresh(product)

    db.add_all(
        [
            ProductTagLink(product_id=household.id, tag_id=household_tag.id),
            ProductTagLink(product_id=multi.id, tag_id=multi_tag.id),
            ProductTagLink(product_id=industrial.id, tag_id=industrial_tag.id),
        ]
    )
    await db.commit()

    resp = await async_client.get(
        "/api/manager/products/list",
        headers=headers,
        params={
            "search": marker,
            "category_status": "missing",
            "category_slug": "cat-household",
            "limit": 100,
        },
    )
    assert resp.status_code == 200, resp.text
    ids = {item["id"] for item in resp.json()["items"]}
    assert missing.id in ids
    assert household.id not in ids
    assert multi.id not in ids
    assert industrial.id not in ids

    household_resp = await async_client.get(
        "/api/manager/products/list",
        headers=headers,
        params={"search": marker, "category_slug": "cat-household", "limit": 100},
    )
    assert household_resp.status_code == 200, household_resp.text
    household_ids = {item["id"] for item in household_resp.json()["items"]}
    assert household.id in household_ids
    assert missing.id not in household_ids


@pytest.mark.asyncio
async def test_manager_products_smart_search_respects_category_slug(async_client, db):
    headers = await _auth_headers(async_client)

    household_tag = await _get_or_create_category_tag(db, "cat-household", "Бытовые")
    multi_tag = await _get_or_create_category_tag(db, "cat-multi", "Мульти-сплит")

    marker = "UNITCATSMART456"
    p_house = Product(title=f"{marker} TCL Household", slug=f"{marker.lower()}-house", price=1000, specs={"area_m2": 20}, is_published=True)
    p_multi = Product(title=f"{marker} TCL Multi", slug=f"{marker.lower()}-multi", price=1100, specs={"area_m2": 20}, is_published=True)
    db.add_all([p_house, p_multi])
    await db.commit()
    for p in [p_house, p_multi]:
        await db.refresh(p)

    db.add_all(
        [
            ProductTagLink(product_id=p_house.id, tag_id=household_tag.id),
            ProductTagLink(product_id=p_multi.id, tag_id=multi_tag.id),
        ]
    )
    await db.commit()

    resp = await async_client.get(
        "/api/manager/products/smart-search",
        headers=headers,
        params={"q": marker, "category_slug": "cat-multi", "limit": 100},
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    ids = {item["id"] for item in items}
    assert p_multi.id in ids
    assert p_house.id not in ids


@pytest.mark.asyncio
async def test_manager_products_recommended_sort_boosts_favorites(async_client, db):
    headers = await _auth_headers(async_client)

    household_tag = await _get_or_create_category_tag(db, "cat-household", "Бытовые")
    favorite_tag = (await db.execute(select(Tag).where(Tag.slug == "manager-favorite"))).scalar_one_or_none()
    if favorite_tag is None:
        favorite_group = TagGroup(
            title="Метки менеджера",
            slug="manager-flags-test",
            color="warning",
            is_public=False,
            allow_multiple=True,
        )
        db.add(favorite_group)
        await db.commit()
        await db.refresh(favorite_group)
        favorite_tag = Tag(
            title="Избранное",
            slug="manager-favorite",
            group_id=favorite_group.id,
            is_public=False,
            is_filter=False,
        )
        db.add(favorite_tag)
        await db.commit()
        await db.refresh(favorite_tag)

    marker = "UNITFAV789"
    regular = Product(
        title=f"{marker} Regular",
        slug=f"{marker.lower()}-regular",
        price=1000,
        specs={"area_m2": 25},
        is_published=True,
    )
    favorite = Product(
        title=f"{marker} Favorite",
        slug=f"{marker.lower()}-favorite",
        price=1100,
        specs={"area_m2": 35},
        is_published=True,
    )
    db.add_all([regular, favorite])
    await db.commit()
    await db.refresh(regular)
    await db.refresh(favorite)

    db.add_all(
        [
            ProductTagLink(product_id=regular.id, tag_id=household_tag.id),
            ProductTagLink(product_id=favorite.id, tag_id=household_tag.id),
            ProductTagLink(product_id=favorite.id, tag_id=favorite_tag.id),
        ]
    )
    await db.commit()

    for product in (regular, favorite):
        await ProductLocalStockDAO.upsert(
            session=db,
            product_id=product.id,
            qty=1,
            updated_by="test",
            warehouse_code="vitebsk",
        )

    resp = await async_client.get(
        "/api/manager/products/list",
        headers=headers,
        params={
            "search": marker,
            "category_slug": "cat-household",
            "sort": "recommended",
            "limit": 10,
        },
    )
    assert resp.status_code == 200, resp.text
    slugs = [item["slug"] for item in resp.json()["items"]]
    assert slugs[:2] == [favorite.slug, regular.slug]


@pytest.mark.asyncio
async def test_manager_products_list_supports_catalog_style_filters(async_client, db):
    headers = await _auth_headers(async_client)

    household_tag = await _get_or_create_category_tag(db, "cat-household", "Бытовые")
    mdv = Brand(title="MDV Filter", slug="mdv-filter", is_published=True, sort_order=0)
    haier = Brand(title="Haier Filter", slug="haier-filter", is_published=True, sort_order=2)
    db.add_all([mdv, haier])
    await db.commit()
    await db.refresh(mdv)
    await db.refresh(haier)

    marker = "UNITFILTER321"
    matched = Product(
        title=f"{marker} MDV On-Off WiFi Fresh",
        slug=f"{marker.lower()}-matched",
        price=1000,
        is_inverter=False,
        brand_id=mdv.id,
        is_published=True,
        specs={"area_m2": 25, "__filter_wifi": True, "fresh_air": True, "__filter_min_heat": -25},
    )
    wrong_brand = Product(
        title=f"{marker} Haier On-Off WiFi Fresh",
        slug=f"{marker.lower()}-wrong-brand",
        price=1000,
        is_inverter=False,
        brand_id=haier.id,
        is_published=True,
        specs={"area_m2": 25, "__filter_wifi": True, "fresh_air": True, "__filter_min_heat": -25},
    )
    wrong_compressor = Product(
        title=f"{marker} MDV Inverter WiFi Fresh",
        slug=f"{marker.lower()}-wrong-compressor",
        price=1000,
        is_inverter=True,
        brand_id=mdv.id,
        is_published=True,
        specs={"area_m2": 25, "__filter_wifi": True, "fresh_air": True, "__filter_min_heat": -25},
    )
    db.add_all([matched, wrong_brand, wrong_compressor])
    await db.commit()
    for product in (matched, wrong_brand, wrong_compressor):
        await db.refresh(product)

    db.add_all(
        [
            ProductTagLink(product_id=matched.id, tag_id=household_tag.id),
            ProductTagLink(product_id=wrong_brand.id, tag_id=household_tag.id),
            ProductTagLink(product_id=wrong_compressor.id, tag_id=household_tag.id),
        ]
    )
    await db.commit()

    resp = await async_client.get(
        "/api/manager/products/list",
        headers=headers,
        params={
            "search": marker,
            "category_slug": "cat-household",
            "brand_slugs": ["mdv-filter"],
            "is_inverter": "false",
            "has_wifi": "true",
            "has_fresh_air": "true",
            "heating_min": -20,
            "limit": 10,
        },
    )
    assert resp.status_code == 200, resp.text
    slugs = [item["slug"] for item in resp.json()["items"]]
    assert slugs == [matched.slug]
