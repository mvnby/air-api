"""Round-trip the release DDL on real PostgreSQL and preserve existing leads."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text


@pytest.mark.asyncio
async def test_connector_release_migration_preserves_leads_and_scope_constraints(
    db_engine,
):
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic/versions/f10a2b3c4d5e_connector_first_release.py"
    )
    spec = importlib.util.spec_from_file_location("connector_release_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def check(connection):
        migration.op = Operations(MigrationContext.configure(connection))
        migration.downgrade()
        lead_id = connection.execute(
            text("""
            INSERT INTO lead (tenant_id, storefront_id, status, source, segment_hint,
                              request_text, created_at, updated_at)
            VALUES (1, 1, 'new', 'manager', 'unknown', 'Existing request', now(), now())
            RETURNING id
        """)
        ).scalar_one()
        migration.upgrade()
        names = set(inspect(connection).get_table_names())
        assert {
            "connector_grant",
            "connector_consent",
            "connector_token",
            "connector_authorization_code",
            "connector_auth_event",
            "command_audit_event",
            "personal_task",
        } <= names
        row = connection.execute(
            text("SELECT request_text, version, intake_meta FROM lead WHERE id=:id"),
            {"id": lead_id},
        ).one()
        assert tuple(row) == ("Existing request", 1, None)
        for table, name in (
            ("connector_grant", "fk_connector_grant_storefront_tenant"),
            ("connector_consent", "fk_connector_consent_storefront_tenant"),
            ("personal_task", "fk_personal_task_storefront_tenant"),
        ):
            fk = next(
                fk
                for fk in inspect(connection).get_foreign_keys(table)
                if fk["name"] == name
            )
            assert fk["constrained_columns"] == ["storefront_id", "tenant_id"]
            assert fk["referred_columns"] == ["id", "tenant_id"]
        assert any(
            i["unique"] and i["column_names"] == ["intake_event_key"]
            for i in inspect(connection).get_indexes("lead")
        )
        migration.downgrade()
        assert (
            connection.execute(
                text("SELECT request_text FROM lead WHERE id=:id"), {"id": lead_id}
            ).scalar_one()
            == "Existing request"
        )
        # Restore metadata-compatible schema for subsequent fixtures.
        migration.upgrade()

    async with db_engine.begin() as connection:
        await connection.run_sync(check)
