from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from tests.unit.alembic_chain_test_support import assert_revision_in_single_head_chain


REVISION = "e6f7a8b9c0d1"
HEAD_REVISION = "f9a0b1c2d3e4"


def _migration():
    path = Path("alembic/versions/e6f7a8b9c0d1_add_modular_document_foundation.py")
    spec = importlib.util.spec_from_file_location(
        "modular_document_foundation_migration", path
    )
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_modular_document_foundation_is_single_alembic_head() -> None:
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert assert_revision_in_single_head_chain(scripts, REVISION) == HEAD_REVISION


def test_expand_migration_preserves_legacy_rows_and_removes_foundation_on_sqlite() -> (
    None
):
    engine = create_engine("sqlite:///:memory:")
    connection = engine.connect()
    connection.execute(text("PRAGMA foreign_keys=ON"))
    connection.execute(text("CREATE TABLE tenant (id INTEGER PRIMARY KEY)"))
    connection.execute(
        text(
            "CREATE TABLE document_template ("
            "id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, doc_type VARCHAR NOT NULL, "
            "google_template_id VARCHAR NOT NULL)"
        )
    )
    connection.execute(
        text(
            "CREATE TABLE order_document ("
            "id INTEGER PRIMARY KEY, doc_type VARCHAR NOT NULL, number VARCHAR NOT NULL, "
            "date DATETIME NOT NULL, google_file_id VARCHAR NOT NULL, google_edit_url VARCHAR NOT NULL)"
        )
    )
    connection.execute(
        text(
            "INSERT INTO document_template (id, name, doc_type, google_template_id) "
            "VALUES (1, 'Legacy invoice', 'invoice', 'google-template')"
        )
    )
    connection.execute(
        text(
            "INSERT INTO order_document "
            "(id, doc_type, number, date, google_file_id, google_edit_url) "
            "VALUES (1, 'invoice', 'СФ-2025-001', '2025-01-01', 'file', 'url')"
        )
    )
    migration = _migration()

    try:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        inspector = inspect(connection)
        assert {
            "document_legal_entity",
            "document_artifact",
            "document_template_version",
            "document_number_policy",
            "document_number_sequence",
            "document_number_reservation",
        } <= set(inspector.get_table_names())
        assert {
            "tenant_id",
            "legal_entity_id",
            "internal_reference",
            "official_series",
            "official_period_key",
            "official_number",
            "official_date",
            "status",
        } <= {column["name"] for column in inspector.get_columns("order_document")}
        legacy = connection.execute(
            text(
                "SELECT number, status, tenant_id, official_number "
                "FROM order_document WHERE id = 1"
            )
        ).one()
        assert tuple(legacy) == ("СФ-2025-001", None, None, None)
        assert (
            inspect(connection).get_columns("document_template")[3]["nullable"] is True
        )

        connection.execute(text("INSERT INTO tenant (id) VALUES (1)"))
        connection.execute(
            text(
                "INSERT INTO document_template "
                "(id, name, doc_type, google_template_id, tenant_id) "
                "VALUES (2, 'Native invoice', 'invoice', NULL, 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO order_document "
                "(id, doc_type, number, date, google_file_id, google_edit_url, tenant_id) "
                "VALUES (2, 'invoice', 'doc_internal', '2026-08-26', NULL, NULL, 1)"
            )
        )
        legal_entity_values = {
            "tenant_id": 1,
            "display_name": "Issuer",
            "is_vat_payer": False,
            "is_default": True,
            "requisites": "{}",
            "status": "active",
            "created_at": "2026-08-26T10:00:00+00:00",
            "updated_at": "2026-08-26T10:00:00+00:00",
        }
        connection.execute(
            text(
                "INSERT INTO document_legal_entity "
                "(id, tenant_id, slug, display_name, is_vat_payer, is_default, requisites, "
                "status, created_at, updated_at) "
                "VALUES (1, :tenant_id, 'main', :display_name, :is_vat_payer, :is_default, "
                ":requisites, :status, :created_at, :updated_at)"
            ),
            legal_entity_values,
        )
        connection.execute(
            text(
                "INSERT INTO document_legal_entity "
                "(id, tenant_id, slug, display_name, is_vat_payer, is_default, requisites, "
                "status, created_at, updated_at) "
                "VALUES (3, :tenant_id, 'secondary', 'Secondary issuer', :is_vat_payer, 0, "
                ":requisites, :status, :created_at, :updated_at)"
            ),
            legal_entity_values,
        )
        connection.execute(
            text("UPDATE order_document SET legal_entity_id = 1 WHERE id = 2")
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO document_number_reservation "
                    "(id, tenant_id, legal_entity_id, document_id, document_type, series, "
                    "period_key, number_value, number_text, idempotency_key, status, "
                    "reserved_at, assigned_at) VALUES "
                    "('wrong-issuer', 1, 3, 2, 'invoice', 'C-', '2026', 1, 'C-001', "
                    "'wrong-issuer', 'assigned', '2026-08-26T10:00:00+00:00', "
                    "'2026-08-26T10:00:00+00:00')"
                )
            )
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO document_legal_entity "
                    "(id, tenant_id, slug, display_name, is_vat_payer, is_default, requisites, "
                    "status, created_at, updated_at) "
                    "VALUES (2, :tenant_id, 'second', :display_name, :is_vat_payer, :is_default, "
                    ":requisites, :status, :created_at, :updated_at)"
                ),
                legal_entity_values,
            )

        connection.execute(
            text(
                "INSERT INTO order_document "
                "(id, doc_type, number, date, google_file_id, google_edit_url, tenant_id, "
                "legal_entity_id, status, internal_reference, replaces_document_id) "
                "VALUES (3, 'invoice', 'replacement-1', '2026-08-26', NULL, NULL, 1, 1, "
                "'draft', 'replacement-1', 2)"
            )
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO order_document "
                    "(id, doc_type, number, date, google_file_id, google_edit_url, tenant_id, "
                    "legal_entity_id, status, internal_reference, replaces_document_id) "
                    "VALUES (4, 'invoice', 'replacement-2', '2026-08-26', NULL, NULL, 1, 1, "
                    "'draft', 'replacement-2', 2)"
                )
            )

        artifact_values = {
            "tenant_id": 1,
            "order_document_id": 2,
            "kind": "pdf",
            "provider": "local_private",
            "storage_key": "documents/2.pdf",
            "content_type": "application/pdf",
            "filename": "invoice.pdf",
            "checksum": "a" * 64,
            "size_bytes": 12,
            "is_authoritative": True,
            "created_at": "2026-08-26T10:00:00+00:00",
        }
        connection.execute(
            text(
                "INSERT INTO document_artifact "
                "(id, tenant_id, order_document_id, kind, provider, storage_key, content_type, "
                "filename, checksum_sha256, size_bytes, is_authoritative, created_at) "
                "VALUES ('artifact-1', :tenant_id, :order_document_id, :kind, :provider, "
                ":storage_key, :content_type, :filename, :checksum, :size_bytes, "
                ":is_authoritative, :created_at)"
            ),
            artifact_values,
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO document_artifact "
                    "(id, tenant_id, order_document_id, kind, provider, storage_key, content_type, "
                    "filename, checksum_sha256, size_bytes, is_authoritative, created_at) "
                    "VALUES ('artifact-2', :tenant_id, :order_document_id, :kind, :provider, "
                    "'documents/2-second.pdf', :content_type, :filename, :checksum, :size_bytes, "
                    ":is_authoritative, :created_at)"
                ),
                artifact_values,
            )

        migration.downgrade()
        inspector = inspect(connection)
        assert "document_legal_entity" not in inspector.get_table_names()
        assert "tenant_id" not in {
            column["name"] for column in inspector.get_columns("order_document")
        }
        assert (
            connection.execute(
                text("SELECT number FROM order_document WHERE id = 1")
            ).scalar_one()
            == "СФ-2025-001"
        )
    finally:
        connection.close()
        engine.dispose()
