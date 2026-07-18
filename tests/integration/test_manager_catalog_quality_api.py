import pytest
from sqlmodel import select

from core.config import settings
from models import Product, ProductTagLink, Tag, TagGroup
from models.supplier import ProductSupplierMapping, Supplier, SupplierOffer


async def _auth_headers(async_client) -> dict[str, str]:
    response = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_catalog_quality_report_supports_normalized_workspace_filters(async_client, db):
    headers = await _auth_headers(async_client)
    group = TagGroup(title="Категория", slug="category", is_public=True, allow_multiple=False)
    db.add(group)
    await db.commit()
    await db.refresh(group)
    tag = Tag(
        title="Бытовые",
        slug="cat-household",
        group_id=group.id,
        is_public=True,
        is_filter=True,
    )
    db.add(tag)
    await db.commit()
    await db.refresh(tag)

    marker = "QUALITY-WORKBENCH-TEST"
    product = Product(
        title=f"{marker} misleading multi title",
        slug="quality-workbench-test",
        price=1000,
        area=25,
        power_cooling=2.6,
        is_published=False,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    db.add(ProductTagLink(product_id=product.id, tag_id=tag.id))
    await db.commit()

    response = await async_client.get(
        "/api/manager/catalog-quality/report",
        headers=headers,
        params={
            "q": marker,
            "equipment_type": "cat-household",
            "series_state": "missing",
            "publication": "hidden",
            "only_problems": "false",
            "group_by": "equipment_type",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["meta"]["total"] == 1
    assert payload["total_products"] == 1
    assert payload["items"][0]["product_id"] == product.id
    assert payload["items"][0]["equipment_type"] == "cat-household"
    assert payload["groups"][0]["key"] == "equipment:cat-household"
    assert any(
        option["value"] == "cat-household"
        for option in payload["filter_options"]["equipment_types"]
    )

    supplier = Supplier(name=f"{marker} supplier", code="quality-workbench-supplier")
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)
    offer = SupplierOffer(
        supplier_id=supplier.id,
        external_id="quality-workbench-offer",
        title_raw=product.title,
        qty=7,
        is_active=False,
    )
    db.add(offer)
    await db.commit()
    db.add(
        ProductSupplierMapping(
            product_id=product.id,
            supplier_id=supplier.id,
            external_id=offer.external_id,
            is_active=True,
        )
    )
    await db.commit()

    mapped_response = await async_client.get(
        "/api/manager/catalog-quality/report",
        headers=headers,
        params={"q": marker, "supplier_state": "mapped", "only_problems": "false"},
    )
    assert mapped_response.status_code == 200, mapped_response.text
    mapped_product = mapped_response.json()["items"][0]
    assert mapped_product["supplier_mapping_count"] == 1
    assert mapped_product["available_qty"] == 0
    assert not any(issue["code"] == "missing_supplier_mapping" for issue in mapped_product["issues"])

    missing = await db.execute(select(Product).where(Product.id == product.id))
    assert missing.scalar_one().series_id is None
