import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


FOUNDATION_PATH = Path(
    "alembic/versions/3f7a9c1d2e04_add_communications_outbox_foundation.py"
)
LEASE_REVISION = "4a8b1c2d3e05"
LEASE_PATH = Path(
    "alembic/versions/4a8b1c2d3e05_harden_communication_delivery_leases.py"
)


def _load_migration(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _insert_delivery(
    connection,
    sequence: int,
    *,
    status: str,
    attempts: int,
    max_attempts: int = 3,
    provider_message_id: str | None = None,
    terminal: bool = False,
) -> None:
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    stored_now = now.isoformat()
    connection.execute(
        text(
            """
            INSERT INTO communication_delivery (
                delivery_id, event_id, channel, recipient_key, destination,
                template_key, template_version, render_context, status,
                priority, attempts, max_attempts, available_at,
                provider_message_id, sent_at, finished_at, created_at, updated_at
            ) VALUES (
                :delivery_id, :event_id, 'telegram', :recipient_key, :destination,
                'telegram.website_contact_lead_created', 1, '{}', :status,
                100, :attempts, :max_attempts, :available_at,
                :provider_message_id, :sent_at, :finished_at, :created_at, :updated_at
            )
            """
        ),
        {
            "delivery_id": f"{sequence:032x}",
            "event_id": f"{sequence + 1000:032x}",
            "recipient_key": f"staff:{sequence}",
            "destination": str(100000 + sequence),
            "status": status,
            "attempts": attempts,
            "max_attempts": max_attempts,
            "available_at": stored_now,
            "provider_message_id": provider_message_id,
            "sent_at": stored_now if terminal else None,
            "finished_at": stored_now if terminal else None,
            "created_at": stored_now,
            "updated_at": stored_now,
        },
    )


def test_delivery_lease_hardening_remains_before_communication_runtime_head():
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = script.get_revision(LEASE_REVISION)

    assert script.get_heads() == ["6c0d3e5f7a21"]
    assert revision is not None
    assert revision.down_revision == "3f7a9c1d2e04"


def test_delivery_lease_migration_replays_and_downgrades_on_sqlite():
    foundation = _load_migration("communication_foundation_for_lease", FOUNDATION_PATH)
    lease = _load_migration("communication_delivery_lease_migration", LEASE_PATH)
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        foundation.op = operations
        lease.op = operations
        foundation.upgrade()
        # Foundation-compatible queued rows must survive the additive C1
        # hardening migration unchanged.
        _insert_delivery(connection, 1, status="queued", attempts=0)
        lease.upgrade()

        inspector = inspect(connection)
        assert connection.execute(
            text(
                "SELECT status, attempts FROM communication_delivery "
                "WHERE delivery_id = :delivery_id"
            ),
            {"delivery_id": f"{1:032x}"},
        ).one() == ("queued", 0)

        _insert_delivery(connection, 2, status="retry", attempts=1)
        _insert_delivery(
            connection,
            3,
            status="sent",
            attempts=1,
            provider_message_id="provider-message-3",
            terminal=True,
        )
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                _insert_delivery(
                    connection,
                    4,
                    status="retry",
                    attempts=3,
                    max_attempts=3,
                )
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                _insert_delivery(
                    connection,
                    5,
                    status="sent",
                    attempts=1,
                    provider_message_id=None,
                    terminal=True,
                )
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                _insert_delivery(
                    connection,
                    6,
                    status="retry",
                    attempts=1,
                    provider_message_id="not-allowed-before-sent",
                )

        constraint_names = {
            item["name"]
            for item in inspector.get_check_constraints("communication_delivery")
        }
        assert {
            "ck_delivery_active_attempts_remaining",
            "ck_delivery_attempt_phase",
            "ck_delivery_attempts_within_max",
            "ck_delivery_lease_state",
            "ck_delivery_provider_message_state",
            "ck_delivery_terminal_timestamps",
        }.issubset(constraint_names)
        assert any(
            item["name"] == "ix_communication_delivery_channel_claim"
            and item["column_names"]
            == ["channel", "priority", "available_at", "created_at", "delivery_id"]
            for item in inspector.get_indexes("communication_delivery")
        )
        assert any(
            item["name"] == "ix_communication_delivery_channel_recovery"
            and item["column_names"]
            == ["channel", "lease_expires_at", "created_at", "delivery_id"]
            for item in inspector.get_indexes("communication_delivery")
        )

        lease.downgrade()
        downgraded = inspect(connection)
        assert not {
            "ck_delivery_active_attempts_remaining",
            "ck_delivery_attempt_phase",
            "ck_delivery_attempts_within_max",
            "ck_delivery_lease_state",
            "ck_delivery_provider_message_state",
            "ck_delivery_terminal_timestamps",
        }.intersection(
            item["name"]
            for item in downgraded.get_check_constraints("communication_delivery")
        )
        assert not any(
            item["name"]
            in {
                "ix_communication_delivery_channel_claim",
                "ix_communication_delivery_channel_recovery",
            }
            for item in downgraded.get_indexes("communication_delivery")
        )
        assert "communication_delivery" in downgraded.get_table_names()
        assert any(
            item["name"] == "ck_delivery_status_valid"
            for item in downgraded.get_check_constraints("communication_delivery")
        )
        assert any(
            item["name"] == "ix_communication_delivery_claim"
            for item in downgraded.get_indexes("communication_delivery")
        )
        assert connection.execute(
            text("SELECT count(*) FROM communication_delivery")
        ).scalar_one() == 3

        foundation.downgrade()
        assert "communication_delivery" not in inspect(connection).get_table_names()
