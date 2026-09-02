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


REVISION = "e7a8b9c0d1e2"
HEAD_REVISION = "c42e8f9b5d73"


def _migration():
    path = Path(
        "alembic/versions/e7a8b9c0d1e2_add_document_seller_entity_type.py"
    )
    spec = importlib.util.spec_from_file_location(
        "document_seller_entity_type_migration",
        path,
    )
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_document_seller_entity_type_is_single_alembic_head() -> None:
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert assert_revision_in_single_head_chain(scripts, REVISION) == HEAD_REVISION


def test_migration_infers_existing_individual_entrepreneurs_on_sqlite() -> None:
    engine = create_engine("sqlite:///:memory:")
    connection = engine.connect()
    connection.execute(
        text(
            "CREATE TABLE document_legal_entity ("
            "id INTEGER PRIMARY KEY, "
            "display_name VARCHAR(200) NOT NULL, "
            "legal_name VARCHAR(500) NULL)"
        )
    )
    connection.execute(
        text(
            "INSERT INTO document_legal_entity (id, display_name, legal_name) VALUES "
            "(1, 'ООО МВН', 'Общество с ограниченной ответственностью МВН'), "
            "(2, 'ИП Иванов', 'Индивидуальный предприниматель Иванов Иван'), "
            "(3, 'Предприниматель', 'Индивидуальный предприниматель Петров Петр')"
        )
    )
    migration = _migration()

    try:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        rows = connection.execute(
            text(
                "SELECT id, entity_type FROM document_legal_entity ORDER BY id"
            )
        ).all()
        assert rows == [
            (1, "organization"),
            (2, "individual_entrepreneur"),
            (3, "individual_entrepreneur"),
        ]
        assert "ix_document_legal_entity_entity_type" in {
            item["name"]
            for item in inspect(connection).get_indexes("document_legal_entity")
        }

        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "UPDATE document_legal_entity SET entity_type = 'person' WHERE id = 1"
                )
            )

        migration.downgrade()
        assert "entity_type" not in {
            column["name"]
            for column in inspect(connection).get_columns("document_legal_entity")
        }
    finally:
        connection.close()
        engine.dispose()
