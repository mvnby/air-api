import importlib.util
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from tests.unit.alembic_chain_test_support import assert_revision_in_single_head_chain


def test_migration_is_in_single_head_and_requires_a_key_when_enabled():
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert_revision_in_single_head_chain(scripts, "fe23bc45de67")
    path = Path("alembic/versions/fe23bc45de67_add_deepseek_connection.py")
    spec = importlib.util.spec_from_file_location("deepseek_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.connect() as connection:
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()
            assert connection.execute(text("SELECT COUNT(*) FROM deepseek_connection")).scalar_one() == 0
            columns = {column["name"] for column in inspect(connection).get_columns("deepseek_connection")}
            assert "encrypted_credentials" in columns and "api_key" not in columns
            for statement in (
                "INSERT INTO deepseek_connection (id, enabled) VALUES (2, false)",
                "INSERT INTO deepseek_connection (id, enabled) VALUES (1, true)",
                "INSERT INTO deepseek_connection (id, enabled, encrypted_credentials) VALUES (1, false, 'ciphertext')",
            ):
                with pytest.raises(IntegrityError):
                    connection.execute(text(statement))
            connection.execute(text("INSERT INTO deepseek_connection (id, enabled) VALUES (1, false)"))
            migration.downgrade()
            assert "deepseek_connection" not in inspect(connection).get_table_names()
    finally:
        engine.dispose()
