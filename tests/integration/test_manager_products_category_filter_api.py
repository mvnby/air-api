import pytest
from sqlmodel import select

from core.config import settings
from models import Product, ProductTagLink, Tag, TagGroup


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
    p_house = Product(title=f"{marker} TCL Household", slug=f"{marker.lower()}-house", price=1000, area=20, is_published=True)
    p_multi = Product(title=f"{marker} TCL Multi", slug=f"{marker.lower()}-multi", price=1100, area=20, is_published=True)
    p_ind = Product(title=f"{marker} TCL Industrial", slug=f"{marker.lower()}-ind", price=1200, area=20, is_published=True)
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
async def test_manager_products_smart_search_respects_category_slug(async_client, db):
    headers = await _auth_headers(async_client)

    household_tag = await _get_or_create_category_tag(db, "cat-household", "Бытовые")
    multi_tag = await _get_or_create_category_tag(db, "cat-multi", "Мульти-сплит")

    marker = "UNITCATSMART456"
    p_house = Product(title=f"{marker} TCL Household", slug=f"{marker.lower()}-house", price=1000, area=20, is_published=True)
    p_multi = Product(title=f"{marker} TCL Multi", slug=f"{marker.lower()}-multi", price=1100, area=20, is_published=True)
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
