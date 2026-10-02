"""Exercise the new migration against real PostgreSQL, not metadata-only DDL."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text


@pytest.mark.asyncio
async def test_inbox_migration_upgrade_downgrade_preserves_parent_rows(db_engine):
    path = Path(__file__).resolve().parents[2] / "alembic/versions/fc2d3e4f5a6b_incoming_triage_state.py"
    spec = importlib.util.spec_from_file_location("inbox_triage_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def check(connection):
        migration.op = Operations(MigrationContext.configure(connection))
        migration.downgrade()
        before = connection.execute(text("SELECT COUNT(*) FROM tenant")).scalar()
        migration.upgrade()
        tables = set(inspect(connection).get_table_names())
        assert {"inbox_read_state", "inbox_triage_state", "inbox_event"} <= tables
        checks = inspect(connection).get_check_constraints("inbox_read_state")
        assert any(row["name"] == "ck_inbox_read_identity" for row in checks)
        migration.downgrade()
        assert connection.execute(text("SELECT COUNT(*) FROM tenant")).scalar() == before
        migration.upgrade()

    # Leave the metadata-compatible schema for the next fixture reset.
    async with db_engine.begin() as connection:
        await connection.run_sync(check)
