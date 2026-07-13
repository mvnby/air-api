import importlib.util
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


RUNTIME_REVISION = "5b9c2d4e6f10"
CANARY_SCOPE_REVISION = "6c0d3e5f7a21"
RUNTIME_MIGRATION_PATH = Path(
    "alembic/versions/5b9c2d4e6f10_add_communication_runtime_state.py"
)
CANARY_SCOPE_MIGRATION_PATH = Path(
    "alembic/versions/6c0d3e5f7a21_add_communication_canary_control_scope.py"
)


def _load_migration(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(
        module_name,
        path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_state_is_single_alembic_head_after_attempt_journal():
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    runtime_revision = script.get_revision(RUNTIME_REVISION)
    canary_revision = script.get_revision(CANARY_SCOPE_REVISION)
    assert script.get_heads() == [CANARY_SCOPE_REVISION]
    assert runtime_revision is not None
    assert runtime_revision.down_revision == "5b9c2d3e4f06"
    assert canary_revision is not None
    assert canary_revision.down_revision == RUNTIME_REVISION


def test_runtime_state_migration_seeds_off_and_downgrades_on_sqlite():
    runtime_migration = _load_migration(
        RUNTIME_MIGRATION_PATH,
        "communication_runtime_state_migration",
    )
    canary_migration = _load_migration(
        CANARY_SCOPE_MIGRATION_PATH,
        "communication_canary_control_scope_migration",
    )
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        runtime_migration.op = operations
        canary_migration.op = operations
        runtime_migration.upgrade()
        inspector = inspect(connection)
        assert "communication_runtime_state" in inspector.get_table_names()
        assert connection.execute(
            text(
                "SELECT channel, mode, status "
                "FROM communication_runtime_state"
            )
        ).one() == ("telegram", "off", "stopped")
        legacy_columns = {
            item["name"]
            for item in inspector.get_columns("communication_runtime_state")
        }
        assert "canary_run_id" not in legacy_columns
        assert "control_revision" not in legacy_columns

        # The published runtime revision allowed a visible but unscoped canary
        # no-op. The additive follow-up must not infer a run identity for it.
        connection.execute(
            text(
                "UPDATE communication_runtime_state "
                "SET mode = 'canary'"
            )
        )
        canary_migration.upgrade()
        inspector = inspect(connection)
        assert connection.execute(
            text(
                "SELECT channel, mode, canary_run_id, control_revision, status "
                "FROM communication_runtime_state"
            )
        ).one() == ("telegram", "off", None, 0, "stopped")
        columns = {
            item["name"]: item
            for item in inspector.get_columns("communication_runtime_state")
        }
        assert columns["canary_run_id"]["nullable"] is True
        assert columns["control_revision"]["nullable"] is False
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
            "ck_communication_runtime_canary_scope_valid",
            "ck_communication_runtime_control_revision_non_negative",
            "ck_communication_runtime_status_valid",
        }.issubset(constraint_names)

        invalid_updates = (
            "mode = 'invalid'",
            "mode = 'canary', canary_run_id = NULL",
            "mode = 'off', canary_run_id = "
            "'123e4567-e89b-42d3-a456-426614174000'",
            "control_revision = -1",
        )
        for assignment in invalid_updates:
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(
                        text(
                            "UPDATE communication_runtime_state "
                            f"SET {assignment}"
                        )
                    )

        with connection.begin_nested():
            connection.execute(
                text(
                    "UPDATE communication_runtime_state "
                    "SET mode = 'canary', "
                    "canary_run_id = "
                    "'123e4567-e89b-42d3-a456-426614174000', "
                    "control_revision = 1"
                )
            )
            assert connection.execute(
                text(
                    "SELECT mode, canary_run_id, control_revision "
                    "FROM communication_runtime_state"
                )
            ).one() == (
                "canary",
                "123e4567-e89b-42d3-a456-426614174000",
                1,
            )

        canary_migration.downgrade()
        remaining_columns = {
            item["name"]
            for item in inspect(connection).get_columns(
                "communication_runtime_state"
            )
        }
        assert "canary_run_id" not in remaining_columns
        assert "control_revision" not in remaining_columns
        runtime_migration.downgrade()
        assert "communication_runtime_state" not in inspect(
            connection
        ).get_table_names()
