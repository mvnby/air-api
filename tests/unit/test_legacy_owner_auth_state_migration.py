from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from tests.unit.alembic_chain_test_support import assert_revision_in_single_head_chain


REVISION = "d2b3c4d5e6f7"


def _migration():
    path = Path("alembic/versions/d2b3c4d5e6f7_add_legacy_owner_auth_state.py")
    spec = importlib.util.spec_from_file_location("legacy_owner_auth_state_migration", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def _base_connection():
    engine = create_engine("sqlite:///:memory:")
    connection = engine.connect()
    connection.execute(
        text(
            """
            CREATE TABLE staff_users (
                id INTEGER PRIMARY KEY
            )
            """
        )
    )
    return engine, connection


def test_legacy_owner_auth_state_is_single_alembic_head() -> None:
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert assert_revision_in_single_head_chain(scripts, REVISION) == REVISION


def test_upgrade_seeds_legacy_singleton_and_clean_downgrade() -> None:
    migration = _migration()
    engine, connection = _base_connection()
    try:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        row = connection.execute(
            text(
                "SELECT id, mode, legacy_token_version, owner_staff_user_id "
                "FROM legacy_owner_auth_state"
            )
        ).mappings().one()
        assert dict(row) == {
            "id": 1,
            "mode": "legacy",
            "legacy_token_version": 1,
            "owner_staff_user_id": None,
        }
        migration.downgrade()
        assert "legacy_owner_auth_state" not in inspect(connection).get_table_names()
    finally:
        connection.close()
        engine.dispose()


def test_downgrade_refuses_to_discard_active_cutover_state() -> None:
    migration = _migration()
    engine, connection = _base_connection()
    try:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        connection.execute(text("INSERT INTO staff_users (id) VALUES (7)"))
        connection.execute(
            text(
                "UPDATE legacy_owner_auth_state "
                "SET mode = 'staff_shadow', owner_staff_user_id = 7, "
                "legacy_token_version = 2 WHERE id = 1"
            )
        )
        with pytest.raises(RuntimeError, match="Refusing downgrade"):
            migration.downgrade()
        assert "legacy_owner_auth_state" in inspect(connection).get_table_names()
    finally:
        connection.close()
        engine.dispose()
