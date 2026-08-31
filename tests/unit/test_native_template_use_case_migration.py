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


REVISION = "f9a0b1c2d3e4"


def _migration():
    path = Path(
        "alembic/versions/f9a0b1c2d3e4_add_native_template_use_case.py"
    )
    spec = importlib.util.spec_from_file_location(
        "native_template_use_case_migration",
        path,
    )
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_native_template_use_case_is_single_alembic_head() -> None:
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert assert_revision_in_single_head_chain(scripts, REVISION) == REVISION


def test_migration_adds_scoped_template_metadata_and_is_reversible() -> None:
    engine = create_engine("sqlite:///:memory:")
    connection = engine.connect()
    connection.execute(
        text(
            "CREATE TABLE document_template ("
            "id INTEGER PRIMARY KEY, doc_type VARCHAR(64) NOT NULL)"
        )
    )
    migration = _migration()

    try:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        inspector = inspect(connection)
        columns = {
            item["name"] for item in inspector.get_columns("document_template")
        }
        assert {"contract_scenario", "business_role"} <= columns
        indexes = {
            item["name"] for item in inspector.get_indexes("document_template")
        }
        assert {
            "ix_document_template_contract_scenario",
            "ix_document_template_business_role",
        } <= indexes

        connection.execute(
            text(
                "INSERT INTO document_template "
                "(id, doc_type, contract_scenario, business_role) VALUES "
                "(1, 'contract', 'supply_installation', NULL), "
                "(2, 'invoice', NULL, 'offer')"
            )
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO document_template "
                    "(id, doc_type, contract_scenario) "
                    "VALUES (3, 'invoice', 'services')"
                )
            )
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO document_template "
                    "(id, doc_type, business_role) "
                    "VALUES (4, 'contract', 'offer')"
                )
            )

        migration.downgrade()
        remaining = {
            item["name"] for item in inspect(connection).get_columns("document_template")
        }
        assert remaining == {"id", "doc_type"}
    finally:
        connection.close()
        engine.dispose()
