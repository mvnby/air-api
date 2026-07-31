import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect


REVISION = "d8e7f6a5b4c3"
MIGRATION_PATH = Path(
    "alembic/versions/d8e7f6a5b4c3_add_installation_notification_watermark.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "installation_notification_watermark_migration",
        MIGRATION_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_installation_watermark_precedes_the_single_provider_boundary_head():
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = script.get_revision(REVISION)

    assert script.get_heads() == ["c9e0f1a2b3d4"]
    assert revision is not None
    assert revision.down_revision == "f4d5e6f7a8b9"


def test_watermark_migration_fails_legacy_all_closed_and_is_reversible():
    migration = _load_migration_module()
    engine = create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    runtime_state = sa.Table(
        "communication_runtime_state",
        metadata,
        sa.Column("channel", sa.String(32), primary_key=True),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("canary_run_id", sa.String(36), nullable=True),
        sa.Column("control_revision", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("instance_id", sa.String(128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(100), nullable=True),
        sa.Column("control_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(mode = 'canary' AND canary_run_id IS NOT NULL "
            "AND length(canary_run_id) = 36) OR "
            "(mode IN ('off', 'all') AND canary_run_id IS NULL)",
            name="ck_communication_runtime_canary_scope_valid",
        ),
        sa.CheckConstraint(
            "control_revision >= 0",
            name="ck_communication_runtime_control_revision_non_negative",
        ),
    )
    now = datetime(2026, 7, 27, tzinfo=timezone.utc)

    with engine.begin() as connection:
        metadata.create_all(connection)
        connection.execute(
            runtime_state.insert().values(
                channel="telegram",
                mode="all",
                canary_run_id=None,
                control_revision=7,
                status="stopped",
                control_updated_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        columns = {
            column["name"]: column
            for column in inspect(connection).get_columns(
                "communication_runtime_state"
            )
        }
        checks = {
            check["name"]
            for check in inspect(connection).get_check_constraints(
                "communication_runtime_state"
            )
        }
        assert columns["installation_estimate_watermark_at"]["nullable"] is True
        assert "ck_communication_runtime_all_watermark_required" in checks
        row = connection.execute(
            sa.text(
                "SELECT mode, control_revision, "
                "installation_estimate_watermark_at "
                "FROM communication_runtime_state WHERE channel = 'telegram'"
            )
        ).one()
        assert tuple(row) == ("off", 8, None)

        with pytest.raises(sa.exc.IntegrityError):
            connection.execute(
                sa.text(
                    "UPDATE communication_runtime_state "
                    "SET mode = 'all' WHERE channel = 'telegram'"
                )
            )
        connection.execute(
            sa.text(
                "UPDATE communication_runtime_state "
                "SET mode = 'all', "
                "installation_estimate_watermark_at = :watermark "
                "WHERE channel = 'telegram'"
            ),
            {"watermark": now.isoformat()},
        )

        migration.downgrade()
        assert "installation_estimate_watermark_at" not in {
            column["name"]
            for column in inspect(connection).get_columns(
                "communication_runtime_state"
            )
        }
        downgraded = connection.execute(
            sa.text(
                "SELECT mode, control_revision "
                "FROM communication_runtime_state WHERE channel = 'telegram'"
            )
        ).one()
        assert tuple(downgraded) == ("off", 9)
