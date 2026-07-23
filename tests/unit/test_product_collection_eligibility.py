from models import Product
from services.product_collection_eligibility import ProductCollectionEligibility


def _evaluate(product: Product):
    return ProductCollectionEligibility.evaluate(
        product,
        surface_key="home",
        slot_key="featured_products",
        supply_metrics={"availability_status": "in_stock_now"},
    )


def test_complete_split_is_eligible_for_home():
    product = Product(
        title="Split",
        slug="split",
        product_kind="complete_split_system",
        price=1000,
        main_image="/media/split.webp",
        specs={"area_m2": 25},
        is_published=True,
    )
    assert _evaluate(product).is_eligible


def test_home_eligibility_reports_all_actionable_failures():
    product = Product(
        title="Indoor",
        slug="indoor",
        product_kind="indoor_unit",
        price=0,
        main_image=None,
        specs={},
        is_published=False,
    )
    result = _evaluate(product)
    assert result.reason_codes == (
        "not_published",
        "unsupported_product_kind",
        "missing_price",
        "missing_main_image",
        "missing_card_specs",
    )
