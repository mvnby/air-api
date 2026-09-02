from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def _migration():
    path = Path(
        "alembic/versions/c42e8f9b5d73_add_document_drive_connections.py"
    )
    spec = importlib.util.spec_from_file_location("document_drive_migration", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_migration_creates_encrypted_tenant_connection_table() -> None:
    engine = create_engine("sqlite:///:memory:")
    connection = engine.connect()
    connection.execute(text("CREATE TABLE tenant (id INTEGER PRIMARY KEY)"))
    migration = _migration()
    try:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        columns = {
            column["name"]
            for column in inspect(connection).get_columns(
                "document_drive_connection"
            )
        }
        assert "tenant_id" in columns
        assert "encrypted_credentials" in columns
        assert "connection_key" in columns
        assert "managed_folder_id" in columns
        assert "refresh_token" not in columns
        assert "access_token" not in columns
        migration.downgrade()
        assert "document_drive_connection" not in inspect(connection).get_table_names()
    finally:
        connection.close()
        engine.dispose()
