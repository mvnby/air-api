from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory


REVISION = "f2a3b4c5d6e7"
DOWN_REVISION = "ab02c3d4e5f6"
MIGRATION_PATH = Path(
    "alembic/versions/f2a3b4c5d6e7_add_order_product_catalog_snapshot.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "order_product_catalog_snapshot_migration",
        MIGRATION_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_order_product_catalog_snapshot_is_the_single_alembic_head():
    script = ScriptDirectory.from_config(Config("alembic.ini"))

    assert script.get_heads() == ["f5c6d7e8a9b0"]
    assert script.get_revision("f5c6d7e8a9b0").down_revision == "f4b5c6d7e8f9"
    assert script.get_revision("f4b5c6d7e8f9").down_revision == "f3a4b5c6d7e8"
    assert script.get_revision("f3a4b5c6d7e8").down_revision == REVISION
    assert script.get_revision(REVISION).down_revision == DOWN_REVISION


def test_order_product_catalog_snapshot_is_nullable_and_reversible():
    migration = _load_migration_module()
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE order_product_link "
                "(id INTEGER PRIMARY KEY, price INTEGER NOT NULL DEFAULT 0)"
            )
        )
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        columns = {
            column["name"]: column
            for column in sa.inspect(connection).get_columns(
                "order_product_link"
            )
        }
        assert columns["title_snapshot"]["nullable"] is True
        assert isinstance(columns["title_snapshot"]["type"], sa.Text)
        assert columns["currency_snapshot"]["nullable"] is True
        assert columns["currency_snapshot"]["type"].length == 3

        long_title = "Т" * 700
        connection.execute(
            sa.text(
                "INSERT INTO order_product_link "
                "(id, price, title_snapshot, currency_snapshot) "
                "VALUES (1, 10, :title, 'BYN')"
            ),
            {"title": long_title},
        )
        assert connection.execute(
            sa.text(
                "SELECT title_snapshot FROM order_product_link WHERE id = 1"
            )
        ).scalar_one() == long_title

        migration.downgrade()
        remaining_columns = {
            column["name"]
            for column in sa.inspect(connection).get_columns(
                "order_product_link"
            )
        }
        assert remaining_columns == {"id", "price"}
