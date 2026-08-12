import pytest

from models import Brand, Product, ProductSeries
from services.importer_service import ImporterService


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_importer_preserves_manual_series_and_repairs_specs_mirror(db, monkeypatch):
    brand = Brand(title="Importer Manual", slug="importer-manual")
    db.add(brand)
    await db.flush()
    manual_series = ProductSeries(
        title="Manager Choice",
        slug="manager-choice",
        brand_id=brand.id,
    )
    db.add(manual_series)
    await db.flush()
    product = Product(
        title="Importer Manual Product",
        slug="importer-manual-product",
        price=1000,
        brand_id=brand.id,
        series_id=manual_series.id,
        series_assignment_source="manual",
        specs={"series": manual_series.title, "brand": brand.title},
        source_url="https://example.test/manual-product",
    )
    db.add(product)
    await db.commit()

    class _Parser:
        def supports(self, url):
            return True

        async def parse(self, url):
            return {
                "title": product.title,
                "slug": product.slug,
                "description": "Imported description",
                "price": 1100,
                "source_url": url,
                "categories": [],
                "metrics": {},
                "specs": {"brand": brand.title, "Серия": "Donor Stale Series"},
            }

    monkeypatch.setattr(
        "services.importer_service.async_session_maker",
        lambda: _SessionContext(db),
    )
    importer = ImporterService()
    importer.parsers = [_Parser()]

    result = await importer.import_product(product.source_url, update_existing=True)

    assert result["product"].series_id == manual_series.id
    assert result["product"].series_assignment_source == "manual"
    assert result["product"].specs["series"] == "Manager Choice"
    assert "Серия" not in result["product"].specs
