from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from tests.unit.alembic_chain_test_support import assert_revision_in_single_head_chain


HEAD_REVISION = "e5f6a7b8c9d0"


def _migration():
    path = Path("alembic/versions/e3c4d5e6f7a8_add_analytics_connections.py")
    spec = importlib.util.spec_from_file_location("analytics_connection_migration", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_analytics_connection_is_single_alembic_head() -> None:
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert (
        assert_revision_in_single_head_chain(scripts, "e3c4d5e6f7a8")
        == HEAD_REVISION
    )


def test_upgrade_creates_encrypted_storefront_connection_table() -> None:
    engine = create_engine("sqlite:///:memory:")
    connection = engine.connect()
    connection.execute(text("CREATE TABLE tenant (id INTEGER PRIMARY KEY)"))
    connection.execute(
        text(
            "CREATE TABLE storefront ("
            "id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, "
            "UNIQUE (id, tenant_id))"
        )
    )
    migration = _migration()
    try:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        columns = {column["name"] for column in inspect(connection).get_columns("analytics_connection")}
        assert "encrypted_credentials" in columns
        assert "credentials_fingerprint" in columns
        assert "oauth_token" not in columns
        assert "access_token" not in columns
        migration.downgrade()
        assert "analytics_connection" not in inspect(connection).get_table_names()
    finally:
        connection.close()
        engine.dispose()
