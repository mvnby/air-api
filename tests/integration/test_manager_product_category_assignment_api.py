import pytest

from models import Product, ProductTagLink
from tests.integration.test_manager_products_category_filter_api import (
    _auth_headers,
    _get_or_create_category_tag,
)


@pytest.mark.asyncio
async def test_manual_category_round_trip_moves_manager_and_public_results(async_client, db):
    headers = await _auth_headers(async_client)
    industrial = await _get_or_create_category_tag(db, "cat-industrial", "Полупромышленные")
    product = Product(
        title="CATEGORYASSIGN TCL Console",
        slug="categoryassign-tcl-console",
        price=2111,
        product_kind="complete_split_system",
        specs={"type": "сплит-система", "indoor_type": "настенный"},
        is_published=True,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    product_id = product.id
    db.add(ProductTagLink(product_id=product_id, tag_id=industrial.id))
    await db.commit()

    response = await async_client.patch(
        f"/api/manager/products/{product_id}",
        headers=headers,
        json={
            "catalog_category_override": "cat-household",
            "product_kind": "complete_split_system",
            "specs": {"type": "сплит-система", "indoor_type": "консольный"},
            "tag_ids": [industrial.id],
        },
    )
    assert response.status_code == 200, response.text

    # Even an older editor submitting stale tag IDs cannot undo the manager choice.
    response = await async_client.patch(
        f"/api/manager/products/{product_id}", headers=headers,
        json={"price": 2222, "tag_ids": [industrial.id]},
    )
    assert response.status_code == 200, response.text
    detail = await async_client.get(f"/api/manager/products/{product_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["catalog_category_override"] == "cat-household"
    assert detail.json()["catalog_category"] == "cat-household"
    assert detail.json()["specs"]["indoor_type"] == "консольный"
    assert detail.json()["price"] == 2222
    assert detail.json()["product_kind"] == "complete_split_system"

    for category, expected_ids in (("cat-household", {product_id}), ("cat-industrial", set())):
        for path, params, authenticated in (
            ("/api/manager/products/list", {"search": "CATEGORYASSIGN", "category_slug": category}, True),
            ("/api/manager/products/smart-search", {"q": "CATEGORYASSIGN", "category_slug": category}, True),
            ("/api/v1/products", {"q": "CATEGORYASSIGN", "tag_slugs": category}, False),
        ):
            result = await async_client.get(path, params=params, headers=headers if authenticated else {})
            assert result.status_code == 200, result.text
            assert {item["id"] for item in result.json()["items"]} == expected_ids

    response = await async_client.patch(
        f"/api/manager/products/{product_id}", headers=headers,
        json={
            "catalog_category_override": None,
            "specs": {"type": "полупромышленный кондиционер", "indoor_type": "кассетный"},
        },
    )
    assert response.status_code == 200, response.text
    detail = await async_client.get(f"/api/manager/products/{product_id}", headers=headers)
    assert detail.json()["catalog_category_override"] is None
    assert detail.json()["catalog_category"] == "cat-industrial"

    response = await async_client.patch(
        f"/api/manager/products/{product_id}", headers=headers,
        json={"catalog_category_override": "cat-missing"},
    )
    assert response.status_code == 422
