import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from tests.unit.alembic_chain_test_support import assert_revision_in_single_head_chain


def test_catalog_usage_migration_extends_current_single_head():
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert_revision_in_single_head_chain(scripts, "e62c3d4e5f6")
    assert scripts.get_revision("e62c3d4e5f6").down_revision == "e61d4e5f6a7"


def test_catalog_usage_migration_has_only_anonymous_aggregate_columns():
    path = Path("alembic/versions/e62c3d4e5f6_add_catalog_workspace_usage.py")
    spec = importlib.util.spec_from_file_location("catalog_usage_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert {column["name"] for column in inspect(connection).get_columns("catalog_workspace_usage_daily")} == {
            "id", "day", "layout_version", "device", "action", "outcome", "duration_bucket", "count",
        }
        migration.downgrade()
        assert "catalog_workspace_usage_daily" not in inspect(connection).get_table_names()
    engine.dispose()
