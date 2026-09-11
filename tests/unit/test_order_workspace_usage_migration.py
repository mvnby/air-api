import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from tests.unit.alembic_chain_test_support import assert_revision_in_single_head_chain


def test_usage_migration_has_one_head_after_product_description():
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert_revision_in_single_head_chain(scripts, "e54a0b1d7f95")
    assert scripts.get_revision("e54a0b1d7f95").down_revision == "d43f9a0c6e84"


def test_usage_upgrade_stores_only_aggregate_dimensions_and_downgrade_preserves_existing_data():
    path = Path("alembic/versions/e54a0b1d7f95_add_order_workspace_usage.py")
    spec = importlib.util.spec_from_file_location("order_usage_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE tenant (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE storefront (id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, UNIQUE(id, tenant_id))"))
        connection.execute(text("INSERT INTO tenant(id) VALUES (1)"))
        connection.execute(text("INSERT INTO storefront(id, tenant_id) VALUES (1, 1)"))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        schema = inspect(connection)
        assert {column["name"] for column in schema.get_columns("order_workspace_usage_daily")} == {
            "id", "tenant_id", "storefront_id", "day", "layout_version", "workflow", "party_kind", "viewport", "metric", "count",
        }
        assert any(fk["constrained_columns"] == ["storefront_id", "tenant_id"] for fk in schema.get_foreign_keys("order_workspace_usage_daily"))
        migration.downgrade()
        assert "order_workspace_usage_daily" not in inspect(connection).get_table_names()
        assert connection.scalar(text("SELECT COUNT(*) FROM storefront")) == 1
    engine.dispose()
