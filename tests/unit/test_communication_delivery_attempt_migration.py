import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from models import CommunicationDelivery, CommunicationDeliveryAttempt
from services.communications.contracts import (
    InstallationEstimateLeadCreatedPayloadV1,
)
from services.communications.delivery_service import CommunicationDeliveryService
from services.communications.processing_scope import CommunicationProcessingScope
from services.communications.template_registry import (
    INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
    INSTALLATION_ESTIMATE_TEMPLATE_KEY,
)

ALL_SCOPE = CommunicationProcessingScope.all(
    control_revision=0,
    event_created_at_watermark=datetime(2000, 1, 1, tzinfo=timezone.utc),
)

FOUNDATION_PATH = Path(
    "alembic/versions/3f7a9c1d2e04_add_communications_outbox_foundation.py"
)
LEASE_PATH = Path(
    "alembic/versions/4a8b1c2d3e05_harden_communication_delivery_leases.py"
)
ATTEMPT_REVISION = "5b9c2d3e4f06"
ATTEMPT_PATH = Path(
    "alembic/versions/5b9c2d3e4f06_add_communication_delivery_attempt_journal.py"
)
PROVIDER_BOUNDARY_REVISION = "e9a1b2c3d4e5"
PROVIDER_BOUNDARY_PATH = Path(
    "alembic/versions/e9a1b2c3d4e5_add_delivery_provider_boundary.py"
)
NOW = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc).isoformat()
SQLITE_RUNNING_NOW = "2026-07-13 12:00:00.000000"


def _load_migration(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _insert_published_event(connection, sequence: int) -> str:
    event_id = f"{sequence + 1000:032x}"
    connection.execute(
        text("""
            INSERT INTO integration_outbox_event (
                event_id, event_type, schema_version, aggregate_type,
                aggregate_id, deduplication_key, payload, status, priority,
                attempts, max_attempts, available_at, occurred_at,
                published_at, created_at, updated_at
            ) VALUES (
                :event_id, :event_type, 1, 'order', :aggregate_id,
                :deduplication_key, :payload, 'published', 100,
                1, 8, :now, :now, :now, :now, :now
            )
            """),
        {
            "event_id": event_id,
            "event_type": INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
            "aggregate_id": str(sequence),
            "deduplication_key": f"attempt-migration:{sequence}",
            "payload": json.dumps({}),
            "now": NOW,
        },
    )
    return event_id


def _insert_queued_delivery(connection, sequence: int) -> str:
    delivery_id = f"{sequence:032x}"
    event_id = _insert_published_event(connection, sequence)
    connection.execute(
        text("""
            INSERT INTO communication_delivery (
                delivery_id, event_id, channel, recipient_key, destination,
                template_key, template_version, render_context, status,
                priority, attempts, max_attempts, available_at,
                created_at, updated_at
            ) VALUES (
                :delivery_id, :event_id, 'telegram', :recipient_key, :destination,
                :template_key, 1, :render_context, 'queued',
                100, 0, 3, :now, :now, :now
            )
            """),
        {
            "delivery_id": delivery_id,
            "event_id": event_id,
            "recipient_key": f"staff:{sequence}",
            "destination": str(100000 + sequence),
            "template_key": INSTALLATION_ESTIMATE_TEMPLATE_KEY,
            "render_context": json.dumps(
                InstallationEstimateLeadCreatedPayloadV1(
                    order_id=sequence,
                    status="new_lead",
                    name=f"Lead {sequence}",
                    phone="+375291112233",
                    description="Нужна консультация",
                    attachment_count=2,
                    photo_categories=("Внутренний блок", "Наружный блок"),
                ).model_dump(mode="json")
            ),
            "now": NOW,
        },
    )
    return delivery_id


def _insert_running_delivery(connection, sequence: int) -> str:
    delivery_id = f"{sequence:032x}"
    event_id = _insert_published_event(connection, sequence)
    connection.execute(
        text("""
            INSERT INTO communication_delivery (
                delivery_id, event_id, channel, recipient_key, destination,
                template_key, template_version, render_context, status,
                priority, attempts, max_attempts, available_at,
                worker_id, lease_token, lease_expires_at,
                created_at, updated_at
            ) VALUES (
                :delivery_id, :event_id, 'telegram', :recipient_key, :destination,
                :template_key, 1, :render_context, 'running',
                100, 1, 3, :now,
                'migration-worker', :lease_token, :lease_expires_at,
                :now, :now
            )
            """),
        {
            "delivery_id": delivery_id,
            "event_id": event_id,
            "recipient_key": f"staff:{sequence}",
            "destination": str(100000 + sequence),
            "template_key": INSTALLATION_ESTIMATE_TEMPLATE_KEY,
            "render_context": json.dumps(
                InstallationEstimateLeadCreatedPayloadV1(
                    order_id=sequence,
                    status="new_lead",
                    name=f"Lead {sequence}",
                    phone="+375291112233",
                    description="Нужна консультация",
                    attachment_count=2,
                    photo_categories=("Внутренний блок", "Наружный блок"),
                ).model_dump(mode="json")
            ),
            "lease_token": "migration-lease-token".ljust(40, "x"),
            "lease_expires_at": "2026-07-13 12:05:00.000000",
            "now": SQLITE_RUNNING_NOW,
        },
    )
    return delivery_id


def _insert_attempt(
    connection,
    *,
    delivery_id: str,
    attempt_no: int,
    outcome: str,
    finished_at: str | None = None,
    error_category: str | None = None,
    error_code: str | None = None,
    retry_after_seconds: int | None = None,
    provider_latency_ms: int | None = None,
    ambiguous: bool = False,
) -> None:
    connection.execute(
        text("""
            INSERT INTO communication_delivery_attempt (
                delivery_id, attempt_no, started_at, finished_at, outcome,
                error_category, error_code, retry_after_seconds,
                provider_latency_ms, ambiguous
            ) VALUES (
                :delivery_id, :attempt_no, :started_at, :finished_at, :outcome,
                :error_category, :error_code, :retry_after_seconds,
                :provider_latency_ms, :ambiguous
            )
            """),
        {
            "delivery_id": delivery_id,
            "attempt_no": attempt_no,
            "started_at": NOW,
            "finished_at": finished_at,
            "outcome": outcome,
            "error_category": error_category,
            "error_code": error_code,
            "retry_after_seconds": retry_after_seconds,
            "provider_latency_ms": provider_latency_ms,
            "ambiguous": ambiguous,
        },
    )


def test_attempt_journal_stays_in_single_alembic_chain_after_lease_hardening():
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = script.get_revision(ATTEMPT_REVISION)
    provider_boundary_revision = script.get_revision(
        PROVIDER_BOUNDARY_REVISION
    )
    heads = script.get_heads()
    assert len(heads) == 1
    revision_ids = {
        item.revision for item in script.walk_revisions(base="base", head=heads[0])
    }

    assert ATTEMPT_REVISION in revision_ids
    assert "6c0d3e5f7a21" in revision_ids
    assert revision is not None
    assert revision.down_revision == "4a8b1c2d3e05"
    assert provider_boundary_revision is not None
    assert provider_boundary_revision.down_revision == "d8e7f6a5b4c3"


def test_attempt_journal_migration_replays_and_downgrades_on_sqlite():
    foundation = _load_migration("foundation_for_attempt", FOUNDATION_PATH)
    lease = _load_migration("lease_for_attempt", LEASE_PATH)
    attempt = _load_migration("attempt_journal_migration", ATTEMPT_PATH)
    provider_boundary = _load_migration(
        "provider_boundary_migration",
        PROVIDER_BOUNDARY_PATH,
    )
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        foundation.op = operations
        lease.op = operations
        attempt.op = operations
        provider_boundary.op = operations
        foundation.upgrade()
        delivery_id = _insert_queued_delivery(connection, 1)
        running_delivery_id = _insert_running_delivery(connection, 2)
        lease.upgrade()
        attempt.upgrade()
        provider_boundary.upgrade()

        inspector = inspect(connection)
        assert "communication_delivery_attempt" in inspector.get_table_names()
        assert "provider_started_at" in {
            column["name"]
            for column in inspector.get_columns(
                "communication_delivery_attempt"
            )
        }
        assert connection.execute(
            text(
                "SELECT status, attempts FROM communication_delivery "
                "WHERE delivery_id = :delivery_id"
            ),
            {"delivery_id": delivery_id},
        ).one() == ("queued", 0)
        assert connection.execute(
            text(
                "SELECT attempt_no, started_at, finished_at, outcome, ambiguous "
                "FROM communication_delivery_attempt "
                "WHERE delivery_id = :delivery_id"
            ),
            {"delivery_id": running_delivery_id},
        ).one() == (1, SQLITE_RUNNING_NOW, None, "running", False)
        assert connection.execute(
            text(
                "SELECT count(*) FROM communication_delivery_attempt "
                "WHERE delivery_id = :delivery_id"
            ),
            {"delivery_id": delivery_id},
        ).scalar_one() == 0

        assert inspector.get_pk_constraint("communication_delivery_attempt")[
            "constrained_columns"
        ] == ["delivery_id", "attempt_no"]
        foreign_keys = inspector.get_foreign_keys("communication_delivery_attempt")
        assert len(foreign_keys) == 1
        assert foreign_keys[0]["referred_table"] == "communication_delivery"
        assert foreign_keys[0]["constrained_columns"] == ["delivery_id"]
        constraint_names = {
            item["name"]
            for item in inspector.get_check_constraints(
                "communication_delivery_attempt"
            )
        }
        assert {
            "ck_delivery_attempt_ambiguity_state",
            "ck_delivery_attempt_error_state",
            "ck_delivery_attempt_finish_state",
            "ck_delivery_attempt_finished_after_started",
            "ck_delivery_attempt_latency_non_negative",
            "ck_delivery_attempt_latency_state",
            "ck_delivery_attempt_no_positive",
            "ck_delivery_attempt_outcome_valid",
            "ck_delivery_attempt_retry_after_positive",
            "ck_delivery_attempt_retry_after_state",
            "ck_delivery_attempt_provider_after_started",
            "ck_delivery_attempt_provider_before_finished",
        }.issubset(constraint_names)
        assert connection.execute(
            text(
                "SELECT provider_started_at "
                "FROM communication_delivery_attempt "
                "WHERE delivery_id = :delivery_id"
            ),
            {"delivery_id": running_delivery_id},
        ).scalar_one() == SQLITE_RUNNING_NOW
        assert {
            "ix_delivery_attempt_ambiguous_finished",
            "ix_delivery_attempt_error_finished",
            "ix_delivery_attempt_outcome_started",
        }.issubset(
            item["name"]
            for item in inspector.get_indexes("communication_delivery_attempt")
        )

        _insert_attempt(
            connection,
            delivery_id=delivery_id,
            attempt_no=1,
            outcome="running",
        )
        connection.execute(
            text(
                "UPDATE communication_delivery_attempt "
                "SET outcome = 'sent', finished_at = :now, provider_latency_ms = 12 "
                "WHERE delivery_id = :delivery_id AND attempt_no = 1"
            ),
            {"delivery_id": delivery_id, "now": NOW},
        )
        invalid_attempts = [
            {"attempt_no": 2, "outcome": "sent"},
            {"attempt_no": 3, "outcome": "retry", "finished_at": NOW},
            {
                "attempt_no": 8,
                "outcome": "retry",
                "finished_at": NOW,
                "error_category": " ",
                "error_code": "timeout",
            },
            {
                "attempt_no": 4,
                "outcome": "sent",
                "finished_at": NOW,
                "ambiguous": True,
            },
            {
                "attempt_no": 5,
                "outcome": "running",
                "retry_after_seconds": 30,
            },
            {
                "attempt_no": 6,
                "outcome": "canceled",
                "finished_at": NOW,
                "error_category": "recipient",
                "error_code": "inactive",
                "provider_latency_ms": 1,
            },
            {
                "attempt_no": 7,
                "outcome": "retry",
                "finished_at": NOW,
                "error_category": "network",
                "error_code": "timeout",
                "provider_latency_ms": -1,
            },
        ]
        for values in invalid_attempts:
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    _insert_attempt(
                        connection,
                        delivery_id=delivery_id,
                        **values,
                    )

        provider_boundary.downgrade()
        assert "provider_started_at" not in {
            column["name"]
            for column in inspect(connection).get_columns(
                "communication_delivery_attempt"
            )
        }
        attempt.downgrade()
        downgraded = inspect(connection)
        assert "communication_delivery_attempt" not in downgraded.get_table_names()
        assert "communication_delivery" in downgraded.get_table_names()
        assert connection.execute(
            text(
                "SELECT status, attempts FROM communication_delivery "
                "WHERE delivery_id = :delivery_id"
            ),
            {"delivery_id": delivery_id},
        ).one() == ("queued", 0)
        assert connection.execute(
            text(
                "SELECT status, attempts FROM communication_delivery "
                "WHERE delivery_id = :delivery_id"
            ),
            {"delivery_id": running_delivery_id},
        ).one() == ("running", 1)

        lease.downgrade()
        assert "communication_delivery" in inspect(connection).get_table_names()
        foundation.downgrade()
        assert "communication_delivery" not in inspect(connection).get_table_names()


@pytest.mark.asyncio
async def test_attempt_journal_backfills_running_row_for_lease_recovery(tmp_path):
    foundation = _load_migration("foundation_for_recovery", FOUNDATION_PATH)
    lease = _load_migration("lease_for_recovery", LEASE_PATH)
    attempt = _load_migration("attempt_journal_for_recovery", ATTEMPT_PATH)
    provider_boundary = _load_migration(
        "provider_boundary_for_recovery",
        PROVIDER_BOUNDARY_PATH,
    )
    database_path = tmp_path / "attempt-migration-recovery.sqlite3"
    engine = create_engine(f"sqlite:///{database_path}")

    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        foundation.op = operations
        lease.op = operations
        attempt.op = operations
        provider_boundary.op = operations
        foundation.upgrade()
        delivery_id = _insert_running_delivery(connection, 9)
        lease.upgrade()
        attempt.upgrade()
        provider_boundary.upgrade()
    engine.dispose()

    async_engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    factory = sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    try:
        async with factory() as session:
            recovery = await CommunicationDeliveryService.recover_expired_leases(
                session,
                scope=ALL_SCOPE,
                now=datetime(2026, 7, 13, 12, 6, tzinfo=timezone.utc),
            )
            await session.commit()
            assert recovery.retry_count == 0
            assert recovery.dead_count == 1

        async with factory() as session:
            delivery = await session.get(CommunicationDelivery, delivery_id)
            journal = await session.get(
                CommunicationDeliveryAttempt,
                (delivery_id, 1),
            )
            assert delivery is not None and delivery.status == "dead"
            assert journal is not None and journal.outcome == "dead"
            assert journal.error_category == "lease"
            assert journal.error_code == "lease_expired_after_provider"
            assert journal.ambiguous is True
            assert journal.provider_started_at is not None
            assert journal.finished_at is not None
    finally:
        await async_engine.dispose()
