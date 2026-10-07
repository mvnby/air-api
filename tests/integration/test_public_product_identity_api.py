import pytest
from bs4 import BeautifulSoup

from models import Brand, Product, ProductSeries
from parsers.aircond import AircondParser
from services.spec_normalizer import normalize_specs


@pytest.mark.asyncio
@pytest.mark.parametrize("class_label", ["Класс мощности", "Номинальный класс мощности"])
async def test_structured_source_identity_survives_catalog_detail_and_navigation(async_client, db, class_label):
    brand = Brand(title="Identity source", slug="identity-source", is_published=True)
    db.add(brand)
    await db.flush()
    series = ProductSeries(brand_id=brand.id, title="Identity series", slug="identity-series", is_published=True)
    db.add(series)
    await db.flush()
    # Explicit source spec rows exercise the actual parser and shared import
    # normalizer. These are input scenarios, not claims about live source data.
    cases = [
        ("KINGHOME Prestige KWH09ACC-S6DBA2A", "KWH09ACC-S6DBA2A", "9", "09"),
        ("TCL TAC-09CHSD/ZG11IHB", "TAC-09CHSD/ZG11IHB", "09", "09"),
        ("Unknown nominal class 12", "OTHER-09", None, None),
        ("Unstructured title KWH09ACC-S6DBA2A", None, None, None),
    ]
    products = []
    for index, (title, model, raw_class, expected) in enumerate(cases):
        rows = '<tr><th>Мощность охлаждения</th><td>2.6 кВт</td></tr>'
        if model:
            rows += f'<tr><th>Модель</th><td>{model}</td></tr>'
        if raw_class:
            rows += f'<tr><th>{class_label}</th><td>{raw_class}</td></tr>'
        soup = BeautifulSoup(f'<div class="product__specs"><table>{rows}</table></div>', "html.parser")
        specs = normalize_specs(AircondParser._extract_specs(soup), title=title, auto_tag_slugs=[])
        product = Product(title=title, slug=f"identity-product-{index}", price=2000, specs=specs, brand_id=brand.id, series_id=series.id, is_published=True)
        db.add(product)
        products.append((product, model, expected))
    await db.commit()

    for path in ("/api/v1/products", "/api/v1/catalog"):
        catalog = await async_client.get(path, params={"limit": 20})
        assert catalog.status_code == 200, catalog.text
        items = {item["slug"]: item for item in catalog.json()["items"]}
        for product, model, expected in products:
            detail = await async_client.get(f"/api/v1/products/{product.slug}")
            assert detail.status_code == 200, detail.text
            for payload in (items[product.slug], detail.json()):
                assert payload["model_code"] == model
                assert payload["capacity_class"] == expected
                assert payload["title"] == product.title
                assert payload["slug"] == product.slug
            for sibling in detail.json()["series_siblings"]:
                canonical = items[sibling["slug"]]
                assert (sibling["model_code"], sibling["capacity_class"]) == (canonical["model_code"], canonical["capacity_class"])

    search = await async_client.get("/api/v1/products", params={"q": cases[1][0]})
    assert search.status_code == 200, search.text
    assert search.json()["items"][0]["model_code"] == cases[1][1]
    assert search.json()["items"][0]["capacity_class"] == "09"

    helper_search = await async_client.get("/api/products/search", params={"q": cases[1][0]})
    assert helper_search.status_code == 200, helper_search.text
    item = next(item for item in helper_search.json()["items"] if item["slug"] == products[1][0].slug)
    assert (item["model_code"], item["capacity_class"]) == (cases[1][1], "09")

    navigation = await async_client.get("/api/v1/product-series/navigation")
    assert navigation.status_code == 200, navigation.text
    groups = navigation.json()["products"]
    assert products[0][0].slug in groups
    assert groups[products[0][0].slug]["series_siblings"]
    for group in groups.values():
        for sibling in group["series_siblings"]:
            canonical = items[sibling["slug"]]
            assert (sibling["model_code"], sibling["capacity_class"]) == (canonical["model_code"], canonical["capacity_class"])

    series_page = await async_client.get("/api/v1/content/brands/identity-source/series/identity-series")
    assert series_page.status_code == 200, series_page.text
    assert {item["slug"] for item in series_page.json()["products"]} == set(items)
    for item in series_page.json()["products"]:
        canonical = items[item["slug"]]
        assert (item["model_code"], item["capacity_class"]) == (canonical["model_code"], canonical["capacity_class"])
