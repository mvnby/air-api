import pytest
from sqlmodel import select

from core.config import settings
from models import Brand, Product, ProductTagLink, Tag, TagGroup


async def _auth_headers(async_client):
    login_resp = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_manager_product_patch_syncs_brand_entity_and_brand_tag(async_client, db):
    headers = await _auth_headers(async_client)

    brand_group = TagGroup(title="Бренд", slug="brand", allow_multiple=False, is_public=True)
    db.add(brand_group)
    await db.commit()
    await db.refresh(brand_group)

    noise_brand_tag = Tag(
        title="Мульти-сплит-система",
        slug="multi-split-sistema",
        group_id=brand_group.id,
        is_public=True,
        is_filter=True,
    )
    tcl_tag = Tag(
        title="TCL",
        slug="tcl",
        group_id=brand_group.id,
        is_public=True,
        is_filter=True,
    )
    db.add(noise_brand_tag)
    db.add(tcl_tag)
    await db.commit()
    await db.refresh(noise_brand_tag)
    await db.refresh(tcl_tag)

    product = Product(
        title="Кондиционер TCL Test",
        slug="tcl-test-brand-sync-api",
        price=1500,
        specs={"area_m2": 30, "brand": "LG"},
        is_published=True,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)

    db.add(ProductTagLink(product_id=product.id, tag_id=noise_brand_tag.id))
    await db.commit()

    resp = await async_client.patch(
        f"/api/manager/products/{product.id}",
        headers=headers,
        json={"tag_ids": [tcl_tag.id]},
    )
    assert resp.status_code == 200, resp.text

    refreshed = await db.get(Product, product.id)
    assert refreshed is not None
    assert refreshed.brand_id is not None

    brand = (await db.execute(select(Brand).where(Brand.id == refreshed.brand_id))).scalar_one()
    assert brand.slug == "tcl"

    brand_links = (
        await db.execute(
            select(Tag.slug)
            .join(ProductTagLink, ProductTagLink.tag_id == Tag.id)
            .where(ProductTagLink.product_id == refreshed.id)
            .where(Tag.group_id == brand_group.id)
        )
    ).scalars().all()
    assert brand_links == ["tcl"]
