from models import Product
from scripts.backfill_product_kinds import build_backfill_plan


def _product(
    *,
    product_id: int,
    product_kind: str,
    system_type: str,
) -> Product:
    return Product(
        id=product_id,
        title=f"Product {product_id}",
        slug=f"product-{product_id}",
        product_kind=product_kind,
        specs={"type": system_type},
    )


def test_backfill_plan_fills_unknown_kinds_and_is_idempotent():
    products = [
        _product(
            product_id=1,
            product_kind="unknown",
            system_type="сплит-система",
        ),
        _product(
            product_id=2,
            product_kind="unknown",
            system_type="внутренний блок",
        ),
    ]

    plan = build_backfill_plan(products, repair_conflicts=False)

    assert [
        (item.product_id, item.previous_kind, item.next_kind)
        for item in plan
    ] == [
        (1, "unknown", "complete_split_system"),
        (2, "unknown", "indoor_unit"),
    ]

    for item in plan:
        products[item.product_id - 1].product_kind = item.next_kind
    assert build_backfill_plan(products, repair_conflicts=False) == []


def test_backfill_plan_requires_explicit_flag_to_repair_known_conflicts():
    mobile = _product(
        product_id=3,
        product_kind="indoor_unit",
        system_type="мобильный",
    )

    assert build_backfill_plan([mobile], repair_conflicts=False) == []

    plan = build_backfill_plan([mobile], repair_conflicts=True)
    assert len(plan) == 1
    assert plan[0].previous_kind == "indoor_unit"
    assert plan[0].next_kind == "other"
