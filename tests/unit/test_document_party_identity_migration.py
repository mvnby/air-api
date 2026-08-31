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


REVISION = "e8b9c0d1e2f3"
HEAD_REVISION = "f9a0b1c2d3e4"


def _migration():
    path = Path("alembic/versions/e8b9c0d1e2f3_add_document_party_identity.py")
    spec = importlib.util.spec_from_file_location(
        "document_party_identity_migration",
        path,
    )
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_document_party_identity_is_single_alembic_head() -> None:
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert assert_revision_in_single_head_chain(scripts, REVISION) == HEAD_REVISION


def test_migration_backfills_company_signing_mode_on_sqlite() -> None:
    engine = create_engine("sqlite:///:memory:")
    connection = engine.connect()
    connection.execute(
        text("CREATE TABLE customer (id INTEGER PRIMARY KEY, type VARCHAR NOT NULL)")
    )
    connection.execute(
        text(
            "INSERT INTO customer (id, type) VALUES "
            "(1, 'individual'), (2, 'company'), (3, 'individual_entrepreneur')"
        )
    )
    migration = _migration()

    try:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        assert connection.execute(
            text("SELECT id, signing_mode FROM customer ORDER BY id")
        ).all() == [
            (1, "self"),
            (2, "statutory_body"),
            (3, "self"),
        ]
        assert {
            column["name"] for column in inspect(connection).get_columns("customer")
        } >= {
            "city",
            "signing_mode",
        }
        with pytest.raises(IntegrityError):
            connection.execute(
                text("UPDATE customer SET signing_mode = 'certificate' WHERE id = 1")
            )

        migration.downgrade()
        assert {
            column["name"] for column in inspect(connection).get_columns("customer")
        } == {
            "id",
            "type",
        }
    finally:
        connection.close()
        engine.dispose()
