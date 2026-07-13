import importlib.util
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


REVISION = "5b9c2d4e6f10"
MIGRATION_PATH = Path(
    "alembic/versions/5b9c2d4e6f10_add_communication_runtime_state.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "communication_runtime_state_migration",
        MIGRATION_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_state_is_single_alembic_head_after_c1():
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = script.get_revision(REVISION)
    assert script.get_heads() == [REVISION]
    assert revision is not None
    assert revision.down_revision == "4a8b1c2d3e05"


def test_runtime_state_migration_seeds_off_and_downgrades_on_sqlite():
    migration = _load_migration()
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        inspector = inspect(connection)
        assert "communication_runtime_state" in inspector.get_table_names()
        assert connection.execute(
            text(
                "SELECT channel, mode, status FROM communication_runtime_state"
            )
        ).one() == ("telegram", "off", "stopped")
        assert any(
            item["name"] == "ix_communication_runtime_state_heartbeat_at"
            and item["column_names"] == ["heartbeat_at"]
            for item in inspector.get_indexes("communication_runtime_state")
        )
        constraint_names = {
            item["name"]
            for item in inspector.get_check_constraints(
                "communication_runtime_state"
            )
        }
        assert {
            "ck_communication_runtime_channel_nonempty",
            "ck_communication_runtime_mode_valid",
            "ck_communication_runtime_status_valid",
        }.issubset(constraint_names)
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(
                    text(
                        "UPDATE communication_runtime_state SET mode = 'invalid'"
                    )
                )

        migration.downgrade()
        assert "communication_runtime_state" not in inspect(
            connection
        ).get_table_names()
