"""The schema expansion must stop before touching inconsistent old snapshots."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


_MIGRATION = Path(__file__).resolve().parents[2] / "alembic/versions/e68b7c9d0e1f_expand_estimate_money_precision.py"
_SPEC = importlib.util.spec_from_file_location("estimate_money_migration", _MIGRATION)
assert _SPEC and _SPEC.loader
module = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(module)


@pytest.mark.parametrize(
    ("item_amount", "expected_blocker"),
    [(100.4, None), (100.401, "estimate 1"), (99.4, "snapshot totals")],
)
def test_estimate_money_preflight_is_read_only(item_amount, expected_blocker):
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE service_estimate (id INTEGER PRIMARY KEY, subtotal FLOAT, "
            "discount_amount FLOAT, total FLOAT)"
        ))
        connection.execute(text(
            "CREATE TABLE service_estimate_item (id INTEGER PRIMARY KEY, estimate_id INTEGER, line_total FLOAT)"
        ))
        connection.execute(text(
            "INSERT INTO service_estimate VALUES (1, 100.4, 0, 100.4)"
        ))
        connection.execute(text(
            "INSERT INTO service_estimate_item VALUES (1, 1, :amount)"
        ), {"amount": item_amount})
        if expected_blocker:
            with pytest.raises(RuntimeError, match=expected_blocker):
                module._preflight_estimates(connection)
        else:
            module._preflight_estimates(connection)
        assert connection.execute(text("SELECT line_total FROM service_estimate_item")).scalar_one() == item_amount


def test_expansion_keeps_old_integer_service_price():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE service_estimate (id INTEGER PRIMARY KEY, subtotal FLOAT NOT NULL, "
            "discount_amount FLOAT NOT NULL, total FLOAT NOT NULL)"
        ))
        connection.execute(text(
            "CREATE TABLE service_estimate_item (id INTEGER PRIMARY KEY, estimate_id INTEGER, line_total FLOAT NOT NULL)"
        ))
        connection.execute(text(
            "CREATE TABLE order_service_link (id INTEGER PRIMARY KEY, price INTEGER NOT NULL, cost INTEGER NOT NULL)"
        ))
        connection.execute(text("INSERT INTO service_estimate VALUES (1, 200.8, 0, 200.8)"))
        connection.execute(text("INSERT INTO service_estimate_item VALUES (1, 1, 100.4), (2, 1, 100.4)"))
        connection.execute(text("INSERT INTO order_service_link VALUES (1, 200, 50)"))

        context = MigrationContext.configure(connection)
        with Operations.context(context):
            module.upgrade()

        assert connection.execute(text("SELECT price FROM order_service_link")).scalar_one() == 200
        assert str(inspect(connection).get_columns("order_service_link")[1]["type"]).startswith("NUMERIC")
