import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from tests.unit.alembic_chain_test_support import assert_revision_in_single_head_chain


def migration():
    path = Path("alembic/versions/dash20261023snap01_dashboard_snapshots.py")
    spec = importlib.util.spec_from_file_location("dashboard_snapshot_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_snapshot_migration_remains_in_single_head_chain():
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert_revision_in_single_head_chain(scripts, "dash20261023snap01")
    assert scripts.get_revision("dash20261023snap01").down_revision == "kan20261022wait01"


def test_upgrade_and_rollback_preserve_connections_without_backfill_or_secrets():
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE tenant(id INTEGER PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE storefront(id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, UNIQUE(id,tenant_id))"))
            connection.execute(text("CREATE TABLE analytics_connection(id INTEGER PRIMARY KEY, encrypted_credentials TEXT NOT NULL, public_config JSON NOT NULL)"))
            connection.execute(text("INSERT INTO tenant VALUES (2)"))
            connection.execute(text("INSERT INTO storefront VALUES (7,2)"))
            connection.execute(text("INSERT INTO analytics_connection VALUES (11,'preserved-encrypted-secret','{}')"))
            revision = migration()
            revision.op = Operations(MigrationContext.configure(connection))
            revision.upgrade()
            inspector = inspect(connection)
            columns = {c["name"]: c for c in inspector.get_columns("dashboard_analytics_snapshot")}
            assert {"key", "tenant_id", "storefront_id", "configuration_revision", "schema_version", "period_start", "period_end", "payload", "last_success_at", "last_attempt_at", "next_retry_at", "error_code", "failure_count", "lease_token", "lease_until"} <= columns.keys()
            assert not {"oauth_token", "access_token", "encrypted_credentials", "staff_user_id", "unread_count"} & columns.keys()
            assert columns["payload"]["nullable"]
            assert not columns["configuration_revision"]["nullable"]
            assert connection.scalar(text("SELECT COUNT(*) FROM dashboard_analytics_snapshot")) == 0
            existing = connection.execute(text("SELECT encrypted_credentials, snapshot_revision FROM analytics_connection WHERE id=11")).one()
            assert existing == ("preserved-encrypted-secret", "initial")
            foreign_keys = inspector.get_foreign_keys("dashboard_analytics_snapshot")
            assert any(fk["constrained_columns"] == ["storefront_id", "tenant_id"] and fk["referred_columns"] == ["id", "tenant_id"] for fk in foreign_keys)
            indexes = inspector.get_indexes("dashboard_analytics_snapshot")
            assert any(i["name"] == "ix_dashboard_snapshot_scope_source" for i in indexes)
            revision.downgrade()
            assert "dashboard_analytics_snapshot" not in inspect(connection).get_table_names()
            assert "snapshot_revision" not in {c["name"] for c in inspect(connection).get_columns("analytics_connection")}
            assert connection.scalar(text("SELECT encrypted_credentials FROM analytics_connection WHERE id=11")) == "preserved-encrypted-secret"
            # Rolling forward again after rollback is safe and starts empty.
            revision.upgrade()
            assert connection.scalar(text("SELECT COUNT(*) FROM dashboard_analytics_snapshot")) == 0
    finally:
        engine.dispose()
