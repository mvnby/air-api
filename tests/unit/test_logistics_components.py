from models import OrderProductLink, Product
from services.documents.logistics import LogisticsSheetStrategy


def _link(
    *,
    price: int = 1803,
    quantity: int = 1,
    specs: dict | None = None,
    logistics_components: list[dict] | None = None,
) -> OrderProductLink:
    product = Product(
        title="Кондиционер Test-24",
        slug="conditioner-test-24",
        price=price,
        specs={**(specs or {}), "area_m2": 70},
    )
    link = OrderProductLink(
        product_id=1,
        quantity=quantity,
        price=price,
        logistics_components=logistics_components,
    )
    link.product = product
    return link


def test_logistics_default_two_block_split_rounds_inner_to_nearest_10():
    components = [
        {"title": "Внутренний блок MDSAF-24HRN8", "price_weight": 1, "kind": "indoor"},
        {"title": "Наружный блок MDOAF-24HN8", "price_weight": 2, "kind": "outdoor"},
    ]
    rows = LogisticsSheetStrategy._expand_product_link_for_logistics(
        _link(specs={"logistics_components": components})
    )

    assert [row["unit_price"] for row in rows] == [600, 1203]
    assert sum(row["line_total"] for row in rows) == 1803
    assert rows[0]["title"] == "Внутренний блок MDSAF-24HRN8,\nстрана происх. Китай"
    assert rows[1]["title"] == "Наружный блок MDOAF-24HN8,\nстрана происх. Китай"


def test_order_level_logistics_components_override_product_template():
    rows = LogisticsSheetStrategy._expand_product_link_for_logistics(
        _link(
            specs={
                "logistics_components": [
                    {"title": "Внутренний блок из товара", "price_weight": 1},
                    {"title": "Наружный блок из товара", "price_weight": 2},
                ]
            },
            logistics_components=[
                {"title": "Позиция заказа 1", "country": "Китай", "unit_price": 700},
                {"title": "Позиция заказа 2", "country": "Китай", "unit_price": 1103},
            ],
        )
    )

    assert [row["title"] for row in rows] == [
        "Позиция заказа 1,\nстрана происх. Китай",
        "Позиция заказа 2,\nстрана происх. Китай",
    ]
    assert [row["unit_price"] for row in rows] == [700, 1103]
    assert sum(row["line_total"] for row in rows) == 1803


def test_product_specs_template_expands_multiple_components_and_keeps_total():
    rows = LogisticsSheetStrategy._expand_product_link_for_logistics(
        _link(
            price=2500,
            specs={
                "country": "Китай",
                "logistics_components": [
                    {"title": "Внутренний кассетный блок", "price_weight": 1},
                    {"title": "Наружный блок", "price_weight": 2},
                    {"title": "Декоративная панель", "price_weight": 0.5, "kind": "accessory"},
                ],
            },
        )
    )

    assert len(rows) == 3
    assert rows[0]["unit_price"] == 710
    assert rows[1]["unit_price"] == 1430
    assert rows[2]["unit_price"] == 360
    assert sum(row["line_total"] for row in rows) == 2500


def test_logistics_fallback_keeps_single_product_row():
    rows = LogisticsSheetStrategy._expand_product_link_for_logistics(
        _link(quantity=2, specs={})
    )

    assert len(rows) == 1
    assert rows[0]["title"] == "Кондиционер Test-24,\nстрана происх. Китай"
    assert rows[0]["quantity"] == 2
    assert rows[0]["unit_price"] == 1803
    assert rows[0]["line_total"] == 3606
