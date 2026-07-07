import pytest
from httpx import AsyncClient

from models import Brand, BrandFeature, Product


@pytest.mark.asyncio
async def test_public_brands_include_only_published_brands_with_published_products(
    async_client: AsyncClient,
    db,
):
    tcl = Brand(
        title="TCL",
        slug="tcl",
        logo_url="/media/brands/tcl.svg",
        description="Кондиционеры TCL для квартир и офисов.",
        is_published=True,
        sort_order=20,
    )
    mdv = Brand(title="MDV", slug="mdv", is_published=True, sort_order=10)
    hidden = Brand(title="Hidden", slug="hidden", is_published=False, sort_order=0)
    empty = Brand(title="Empty", slug="empty", is_published=True, sort_order=30)
    db.add_all([tcl, mdv, hidden, empty])
    await db.flush()
    db.add_all(
        [
            BrandFeature(
                brand_id=tcl.id,
                title="Fresh Air",
                slug="fresh-air",
                text="Фильтрация воздуха в бытовых сериях.",
                image_url="/media/brands/tcl/fresh-air.webp",
                icon="air",
                footnote="Доступно не во всех моделях",
                aliases=["filter"],
                is_published=True,
                sort_order=20,
            ),
            BrandFeature(
                brand_id=tcl.id,
                title="Draft feature",
                slug="draft-feature",
                is_published=False,
                sort_order=10,
            ),
        ]
    )

    db.add_all(
        [
            Product(
                title="TCL published",
                slug="tcl-published",
                price=1000,
                area=25,
                brand_id=tcl.id,
                is_published=True,
            ),
            Product(
                title="TCL draft",
                slug="tcl-draft",
                price=1000,
                area=25,
                brand_id=tcl.id,
                is_published=False,
            ),
            Product(
                title="MDV published",
                slug="mdv-published",
                price=1000,
                area=25,
                brand_id=mdv.id,
                is_published=True,
            ),
            Product(
                title="Hidden published",
                slug="hidden-published",
                price=1000,
                area=25,
                brand_id=hidden.id,
                is_published=True,
            ),
        ]
    )
    await db.commit()

    response = await async_client.get("/api/v1/content/brands")
    assert response.status_code == 200, response.text
    items = response.json()
    assert [item["slug"] for item in items] == ["mdv", "tcl"]

    tcl_payload = next(item for item in items if item["slug"] == "tcl")
    assert tcl_payload == {
        "id": tcl.id,
        "title": "TCL",
        "slug": "tcl",
        "logo_url": "/media/brands/tcl.svg",
        "description": "Кондиционеры TCL для квартир и офисов.",
        "products_count": 1,
        "sort_order": 20,
    }

    detail_response = await async_client.get("/api/v1/content/brands/tcl")
    assert detail_response.status_code == 200, detail_response.text
    detail_payload = detail_response.json()
    assert detail_payload["products_count"] == 1
    assert detail_payload["features"] == [
        {
            "id": detail_payload["features"][0]["id"],
            "title": "Fresh Air",
            "slug": "fresh-air",
            "text": "Фильтрация воздуха в бытовых сериях.",
            "image_url": "/media/brands/tcl/fresh-air.webp",
            "icon": "air",
            "footnote": "Доступно не во всех моделях",
            "source_url": None,
            "aliases": ["filter"],
            "is_published": True,
            "sort_order": 20,
        }
    ]

    for slug in ("hidden", "empty", "missing"):
        missing_response = await async_client.get(f"/api/v1/content/brands/{slug}")
        assert missing_response.status_code == 404
