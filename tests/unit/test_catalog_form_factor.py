import json
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlmodel import select

from models import Product
from services.catalog_form_factor import indoor_form_factor_expr


def test_visible_indoor_type_wins_over_missing_or_stale_derived_values():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    session = SimpleNamespace(bind=engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE product (id INTEGER PRIMARY KEY, specs TEXT)")
        rows = (
            (1, {"indoor_type": "настенный", "__typed_specs": {"indoor_type": {"value": "настенный"}}}),
            (2, {"indoor_type": "консольный", "__typed_specs": {"indoor_type": {"value": "column"}}, "__filter_indoor_type": "column"}),
            (3, {"__typed_specs": {"indoor_type": {"value": "кассетный"}}}),
            (4, {"__filter_indoor_type": "duct"}),
        )
        for product_id, specs in rows:
            connection.exec_driver_sql("INSERT INTO product (id, specs) VALUES (?, ?)", (product_id, json.dumps(specs, ensure_ascii=False)))

        result = connection.execute(select(Product.id, indoor_form_factor_expr(session)).order_by(Product.id)).all()

    assert result == [(1, "wall"), (2, "console"), (3, "cassette"), (4, "duct")]
