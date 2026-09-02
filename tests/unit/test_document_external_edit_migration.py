from __future__ import annotations

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


REVISION = "b31d9e7a4c62"


def _migration():
    path = Path("alembic/versions/b31d9e7a4c62_add_document_external_edit_sessions.py")
    spec = importlib.util.spec_from_file_location(
        "document_external_edit_migration", path
    )
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_external_edit_revision_is_in_single_head_chain() -> None:
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert_revision_in_single_head_chain(scripts, REVISION)


def test_external_edit_migration_enforces_one_provider_neutral_subject() -> None:
    engine = create_engine("sqlite:///:memory:")
    connection = engine.connect()
    connection.execute(text("PRAGMA foreign_keys=ON"))
    connection.execute(text("CREATE TABLE tenant (id INTEGER PRIMARY KEY)"))
    connection.execute(
        text("CREATE TABLE document_template_version (id INTEGER PRIMARY KEY)")
    )
    connection.execute(
        text("CREATE TABLE document_artifact (id VARCHAR(32) PRIMARY KEY)")
    )
    connection.execute(text("CREATE TABLE staff_users (id INTEGER PRIMARY KEY)"))
    migration = _migration()
    try:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        columns = {
            item["name"]
            for item in inspect(connection).get_columns(
                "document_external_edit_session"
            )
        }
        assert {
            "template_version_id",
            "document_artifact_id",
            "provider_connection_id",
            "remote_file_id",
            "remote_revision",
            "base_checksum_sha256",
            "active_sync_key",
            "active_sync_fingerprint",
            "last_sync_key",
            "last_sync_fingerprint",
            "created_by_staff_user_id",
            "last_synced_by_staff_user_id",
        } <= columns

        connection.execute(text("INSERT INTO tenant (id) VALUES (1)"))
        connection.execute(
            text("INSERT INTO document_template_version (id) VALUES (10)")
        )
        connection.execute(
            text("INSERT INTO document_artifact (id) VALUES ('artifact-1')")
        )
        base = (
            "INSERT INTO document_external_edit_session "
            "(id, tenant_id, subject_type, template_version_id, "
            "document_artifact_id, provider, provider_connection_id, "
            "base_checksum_sha256, status, created_at, updated_at) VALUES "
        )
        connection.execute(
            text(
                base + "('session-1', 1, 'template_version', 10, NULL, "
                "'google_drive', 'connection-1', :checksum, 'ready', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"checksum": "a" * 64},
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    base + "('session-2', 1, 'template_version', 10, "
                    "'artifact-1', 'google_drive', 'connection-1', :checksum, "
                    "'ready', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"checksum": "b" * 64},
            )
        connection.rollback()

        migration.downgrade()
        assert (
            "document_external_edit_session"
            not in inspect(connection).get_table_names()
        )
    finally:
        connection.close()
        engine.dispose()
