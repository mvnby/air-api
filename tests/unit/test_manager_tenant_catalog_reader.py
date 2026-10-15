from models import Product, ProductImage, ProductImageVariant
from services.manager_tenant_catalog_reader import _content_images, product_reader_specifications


def test_reader_projects_registered_legacy_specs_with_units_and_no_private_metadata():
    product = Product(
        title="Reader", slug="reader", price=2000, is_inverter=True,
        specs={
            "Мощность охлаждения": "3.5 кВт",
            "area_m2": 35,
            "wifi_ready": "ready",
            "weight_indoor": "8.5 кг",
            "indoor_type": "кассетный",
            "warranty_months": "36",
            "__typed_specs": {"supplier_secret": {"value": "PRIVATE"}},
            "source_url": "https://supplier.example/PRIVATE",
            "credentials": "PRIVATE",
            "Supplier note": "PRIVATE",
        },
    )
    groups, summary = product_reader_specifications(product)
    items = {item["key"]: item for group in groups for item in group["items"]}
    assert items["capacity_cooling_kw"] == {
        "key": "capacity_cooling_kw", "label": "Мощность охлаждения", "value": "3.5", "unit": "кВт",
    }
    assert items["area_m2"]["value"] == "35"
    assert items["area_m2"]["unit"] == "м²"
    assert items["wifi_state"]["value"] == "Опция"
    assert items["inverter"]["value"] == "Да"
    assert items["weight_indoor"]["value"] == "8.5"
    assert items["indoor_type"]["value"] == "кассетный"
    assert items["warranty_months"]["unit"] == "мес."
    assert "PRIVATE" not in str(groups)
    assert {item["key"] for item in summary} >= {"area_m2", "capacity_cooling_kw", "inverter"}


def test_reader_keeps_false_zero_and_all_temperature_bounds():
    product = Product(
        title="Reader", slug="reader", price=1,
        specs={"inverter": False, "current_cooling_nominal_a": 0, "temp_range_heat": "-25 … 24"},
    )
    groups, _ = product_reader_specifications(product)
    items = {item["key"]: item for group in groups for item in group["items"]}
    assert items["inverter"]["value"] == "Нет"
    assert items["current_cooling_nominal_a"]["value"] == "0"
    assert "-25" in items["temp_range_heat"]["value"]
    assert "24" in items["temp_range_heat"]["value"]


def test_reader_gallery_uses_public_original_and_approved_full_variant():
    product = Product(
        title="Reader", slug="reader", price=1, main_image="https://supplier.example/source.webp",
        images=["https://supplier.example/source.webp", "/media/legacy.webp", "javascript:alert(1)"],
    )
    image = ProductImage(id=1, product_id=1, url="https://supplier.example/source.webp")
    image.variants = [
        ProductImageVariant(product_image_id=1, variant_type="original", processing_status="ready", url="/media/public.webp"),
        ProductImageVariant(product_image_id=1, variant_type="full", processing_status="ready", manual_quality_status="approved", url="/media/full.webp"),
        ProductImageVariant(product_image_id=1, variant_type="card", processing_status="ready", manual_quality_status="unreviewed", url="/media/private.webp"),
    ]
    product.gallery_images = [image]
    main, images = _content_images(product)
    assert main == "/media/public.webp"
    assert [item["url"] for item in images] == ["/media/public.webp", "/media/full.webp", "/media/legacy.webp"]
