import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from tests.unit.alembic_chain_test_support import assert_revision_in_single_head_chain


def test_permissions_migration_preserves_memberships_without_implicit_grants():
    path = Path("alembic/versions/t1161access01_membership_permissions.py")
    spec = importlib.util.spec_from_file_location("membership_permissions_migration", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert_revision_in_single_head_chain(scripts, migration.revision)
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE tenant_membership (id INTEGER PRIMARY KEY, role TEXT NOT NULL)"))
            connection.execute(text("INSERT INTO tenant_membership (id, role) VALUES (1, 'owner'), (2, 'manager')"))
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()
            rows = connection.execute(text("SELECT id, role, permissions FROM tenant_membership ORDER BY id")).all()
            assert rows == [(1, "owner", "[]"), (2, "manager", "[]")]
            connection.execute(text("INSERT INTO tenant_membership (id, role) VALUES (3, 'catalog_editor')"))
            assert connection.scalar(text("SELECT permissions FROM tenant_membership WHERE id = 3")) == "[]"
            columns = {column["name"]: column for column in inspect(connection).get_columns("tenant_membership")}
            assert columns["permissions"]["nullable"] is False
            migration.downgrade()
            assert "permissions" not in {column["name"] for column in inspect(connection).get_columns("tenant_membership")}
            assert connection.scalar(text("SELECT count(*) FROM tenant_membership")) == 3
    finally:
        engine.dispose()
