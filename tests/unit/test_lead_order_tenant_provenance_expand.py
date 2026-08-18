import importlib.util
from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlmodel import SQLModel

import models  # noqa: F401 - registers SQLModel tables for metadata assertions
from tests.unit.alembic_chain_test_support import (
    assert_revision_in_single_head_chain,
)


REVISION = "f6b2a4d8e1c3"
PROVENANCE_BOUNDARY_REVISION = "a7c8d9e0f1b2"
CUSTOMER_SCOPE_REVISION = "b8d9e0f1a2c3"
CONTRACT_REVISION = "c9e0f1a2b3d4"
STOREFRONT_IDEMPOTENCY_REVISION = "d0f1a2b3c4d5"
TENANT_OFFER_REVISION = "d0a1b2c3e4f6"
PREVIOUS_HEAD_REVISION = "f5c6d7e8a9b0"
WEBSITE_CANARY_REVISION = "ab02c3d4e5f6"
PUBLIC_WRITE_REVISION = "aa91c2d4e6f8"
CATALOG_REVISION = "e1f2a3b4c5d6"
MIGRATION_PATH = Path("alembic/versions/f6b2a4d8e1c3_add_lead_order_tenant_provenance_expand.py")


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("lead_order_tenant_provenance_expand", MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_legacy_schema(connection) -> None:
    connection.execute(text("CREATE TABLE tenant (id INTEGER PRIMARY KEY)"))
    connection.execute(text("CREATE TABLE storefront (id INTEGER PRIMARY KEY)"))
    connection.execute(
        text(
            """
            CREATE TABLE lead (
                id INTEGER PRIMARY KEY,
                status VARCHAR(24),
                created_at DATETIME NOT NULL
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE TABLE "order" (
                id INTEGER PRIMARY KEY,
                status VARCHAR(24),
                created_at DATETIME NOT NULL
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE TABLE order_child (
                id INTEGER PRIMARY KEY,
                order_id INTEGER NOT NULL REFERENCES "order" (id)
            )
            """
        )
    )
    connection.execute(text("INSERT INTO lead (id, status, created_at) VALUES (1, 'new', '2026-01-01')"))
    connection.execute(text("INSERT INTO \"order\" (id, status, created_at) VALUES (1, 'new_lead', '2026-01-01')"))
    connection.execute(text("INSERT INTO order_child (id, order_id) VALUES (1, 1)"))


def test_lead_order_tenant_provenance_expand_is_in_single_head_chain():
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = script.get_revision(REVISION)
    assert_revision_in_single_head_chain(script, REVISION)
    assert revision is not None
    assert revision.down_revision == "e9a1b2c3d4e5"
    assert script.get_revision(PREVIOUS_HEAD_REVISION).down_revision == "f4b5c6d7e8f9"
    assert script.get_revision("f4b5c6d7e8f9").down_revision == "f3a4b5c6d7e8"
    assert script.get_revision("f3a4b5c6d7e8").down_revision == "f2a3b4c5d6e7"
    assert script.get_revision("f2a3b4c5d6e7").down_revision == WEBSITE_CANARY_REVISION
    assert (
        script.get_revision(WEBSITE_CANARY_REVISION).down_revision
        == PUBLIC_WRITE_REVISION
    )
    assert (
        script.get_revision(PUBLIC_WRITE_REVISION).down_revision
        == CATALOG_REVISION
    )
    assert (
        script.get_revision(CATALOG_REVISION).down_revision
        == TENANT_OFFER_REVISION
    )
    assert (
        script.get_revision(TENANT_OFFER_REVISION).down_revision
        == STOREFRONT_IDEMPOTENCY_REVISION
    )
    assert (
        script.get_revision(STOREFRONT_IDEMPOTENCY_REVISION).down_revision
        == CONTRACT_REVISION
    )
    assert (
        script.get_revision(CONTRACT_REVISION).down_revision
        == CUSTOMER_SCOPE_REVISION
    )
    assert (
        script.get_revision(CUSTOMER_SCOPE_REVISION).down_revision
        == PROVENANCE_BOUNDARY_REVISION
    )
    assert (
        script.get_revision(PROVENANCE_BOUNDARY_REVISION).down_revision
        == REVISION
    )


def test_lead_order_tenant_provenance_expand_is_nullable_and_reversible_on_sqlite():
    migration = _load_migration_module()
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys = ON"))
        _create_legacy_schema(connection)
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        inspector = inspect(connection)

        for table_name in ("lead", "order"):
            columns = {column["name"]: column for column in inspector.get_columns(table_name)}
            assert columns["tenant_id"]["nullable"] is True
            assert columns["storefront_id"]["nullable"] is True
            indexes = {index["name"]: index["column_names"] for index in inspector.get_indexes(table_name)}
            assert indexes[f"ix_{table_name}_tenant_status_created_at"] == ["tenant_id", "status", "created_at"]
            assert indexes[f"ix_{table_name}_storefront_status_created_at"] == ["storefront_id", "status", "created_at"]

        assert connection.execute(text("SELECT tenant_id, storefront_id FROM lead WHERE id = 1")).one() == (None, None)
        assert connection.execute(text("SELECT tenant_id, storefront_id FROM \"order\" WHERE id = 1")).one() == (None, None)

        connection.execute(text("INSERT INTO lead (id, status, created_at) VALUES (2, 'new', '2026-01-02')"))
        connection.execute(text("INSERT INTO \"order\" (id, status, created_at) VALUES (2, 'new_lead', '2026-01-02')"))

        connection.execute(text("INSERT INTO tenant (id) VALUES (10)"))
        connection.execute(text("INSERT INTO storefront (id) VALUES (20)"))
        connection.execute(
            text(
                """
                INSERT INTO lead (id, tenant_id, storefront_id, status, created_at)
                VALUES (3, 10, 20, 'new', '2026-01-03')
                """
            )
        )
        assert connection.execute(text("SELECT order_id FROM order_child WHERE id = 1")).scalar_one() == 1

        with pytest.raises(RuntimeError, match="Refusing to drop tenant provenance"):
            migration.downgrade()
        connection.execute(text("UPDATE lead SET tenant_id = NULL, storefront_id = NULL"))
        connection.execute(text('UPDATE "order" SET tenant_id = NULL, storefront_id = NULL'))
        migration.downgrade()
        for table_name in ("lead", "order"):
            columns = {column["name"] for column in inspect(connection).get_columns(table_name)}
            assert "tenant_id" not in columns
            assert "storefront_id" not in columns
        assert connection.execute(text("SELECT id, status FROM lead WHERE id = 1")).one() == (1, "new")
        assert connection.execute(text("SELECT id, status FROM \"order\" WHERE id = 1")).one() == (1, "new_lead")
        assert connection.execute(text("SELECT order_id FROM order_child WHERE id = 1")).scalar_one() == 1


def test_lead_order_tenant_provenance_expand_emits_postgresql_foreign_keys():
    migration = _load_migration_module()
    output = StringIO()
    context = MigrationContext.configure(
        url="postgresql://",
        opts={"as_sql": True, "output_buffer": output},
    )
    migration.op = Operations(context)

    migration.upgrade()

    ddl = output.getvalue()
    for constraint_name in (
        migration.LEAD_TENANT_FK,
        migration.LEAD_STOREFRONT_FK,
        migration.ORDER_TENANT_FK,
        migration.ORDER_STOREFRONT_FK,
    ):
        assert f"CONSTRAINT {constraint_name}" in ddl
    assert "REFERENCES tenant (id)" in ddl
    assert "REFERENCES storefront (id)" in ddl


def test_lead_order_model_metadata_reflects_contract_phase():
    for table_name in ("lead", "order"):
        table = SQLModel.metadata.tables[table_name]
        assert table.c.tenant_id.nullable is False
        assert table.c.storefront_id.nullable is False
        assert table.c.tenant_id.server_default is None
        assert table.c.storefront_id.server_default is None
        foreign_key_targets = {foreign_key.target_fullname for foreign_key in table.foreign_keys}
        assert "tenant.id" in foreign_key_targets
        assert "storefront.id" in foreign_key_targets
        indexes = {index.name: [column.name for column in index.columns] for index in table.indexes}
        assert indexes[f"ix_{table_name}_tenant_status_created_at"] == ["tenant_id", "status", "created_at"]
        assert indexes[f"ix_{table_name}_storefront_status_created_at"] == ["storefront_id", "status", "created_at"]
