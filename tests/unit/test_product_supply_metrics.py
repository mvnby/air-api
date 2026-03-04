import pytest

from models import GlobalConfig, Product
from models.supplier import ProductLocalStock, ProductSupplierMapping, Supplier, SupplierOffer, SupplierPriceSource
from services.product_supply_metrics_service import ProductSupplyMetricsService


@pytest.mark.asyncio
async def test_compute_product_supply_metrics(db):
    product = Product(title="AC", slug="ac-metrics", price=3000, area=25)
    supplier = Supplier(name="S1", code="s1", priority=1)
    db.add(product)
    db.add(supplier)
    db.add(GlobalConfig(key="fx_rate_usd_byn", value="3.2", description="fx"))
    db.add(GlobalConfig(key="fx_supplier_markup_percent", value="0", description="test"))
    await db.commit()
    await db.refresh(product)
    await db.refresh(supplier)

    db.add(
        SupplierPriceSource(
            supplier_id=supplier.id,
            spreadsheet_id="sheet-1",
            city_bucket="minsk",
            is_active=True,
        )
    )
    db.add(
        SupplierOffer(
            supplier_id=supplier.id,
            external_id="sku-1",
            qty=4,
            wholesale_value=500,
            wholesale_currency="USD",
            rrc_byn=2670,
            is_active=True,
        )
    )
    db.add(
        ProductSupplierMapping(
            product_id=product.id,
            supplier_id=supplier.id,
            external_id="sku-1",
            is_active=True,
        )
    )
    db.add(ProductLocalStock(product_id=product.id, warehouse_code="vitebsk", qty=2))
    await db.commit()

    metrics = await ProductSupplyMetricsService.compute_for_products(db, [product])
    row = metrics[product.id]
    assert row["min_cost_byn"] == 1600.0
    assert row["recommended_price_byn"] == 2670.0
    assert row["margin_abs_preview"] == 1400.0
    assert row["vitebsk_qty"] == 2
    assert row["minsk_qty"] == 4
    assert row["availability_status"] == "in_stock_now"


@pytest.mark.asyncio
async def test_compute_metrics_fallback_cost_for_zero_qty_offer(db):
    product = Product(title="AC2", slug="ac-metrics-2", price=2470, area=25)
    supplier = Supplier(name="S2", code="s2", priority=1)
    db.add(product)
    db.add(supplier)
    db.add(GlobalConfig(key="fx_rate_usd_byn", value="3.2", description="fx"))
    db.add(GlobalConfig(key="fx_supplier_markup_percent", value="0", description="test"))
    await db.commit()
    await db.refresh(product)
    await db.refresh(supplier)

    db.add(
        SupplierPriceSource(
            supplier_id=supplier.id,
            spreadsheet_id="sheet-2",
            city_bucket="minsk",
            is_active=True,
        )
    )
    db.add(
        SupplierOffer(
            supplier_id=supplier.id,
            external_id="sku-2",
            qty=0,
            qty_raw="нет в наличии",
            wholesale_value=549,
            wholesale_currency="USD",
            rrc_byn=2470,
            is_active=True,
        )
    )
    db.add(
        ProductSupplierMapping(
            product_id=product.id,
            supplier_id=supplier.id,
            external_id="sku-2",
            is_active=True,
        )
    )
    await db.commit()

    metrics = await ProductSupplyMetricsService.compute_for_products(db, [product])
    row = metrics[product.id]
    assert row["min_cost_byn"] == 1756.8
    assert row["margin_abs_preview"] == 713.2
    assert row["minsk_qty"] == 0
    assert row["availability_status"] == "out_of_stock"


@pytest.mark.asyncio
async def test_compute_metrics_byn_wholesale_and_incoming_status(db):
    product = Product(title="AC3", slug="ac-metrics-3", price=3330, area=25)
    supplier = Supplier(name="S3", code="s3", priority=1)
    db.add(product)
    db.add(supplier)
    db.add(GlobalConfig(key="fx_rate_usd_byn", value="3.2", description="fx"))
    db.add(GlobalConfig(key="fx_supplier_markup_percent", value="0", description="test"))
    await db.commit()
    await db.refresh(product)
    await db.refresh(supplier)

    db.add(
        SupplierPriceSource(
            supplier_id=supplier.id,
            spreadsheet_id="sheet-3",
            city_bucket="minsk",
            is_active=True,
        )
    )
    db.add(
        SupplierOffer(
            supplier_id=supplier.id,
            external_id="sku-3",
            qty=0,
            qty_raw="приход через 2-3 дня",
            wholesale_value=2165,
            wholesale_currency="BYN",
            rrc_byn=3330,
            is_active=True,
        )
    )
    db.add(
        ProductSupplierMapping(
            product_id=product.id,
            supplier_id=supplier.id,
            external_id="sku-3",
            is_active=True,
        )
    )
    await db.commit()

    metrics = await ProductSupplyMetricsService.compute_for_products(db, [product])
    row = metrics[product.id]
    assert row["min_cost_byn"] == 2165.0
    assert row["margin_abs_preview"] == 1165.0
    assert row["minsk_qty"] == 0
    assert row["availability_status"] == "check_availability"
