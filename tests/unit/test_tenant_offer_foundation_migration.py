import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import inspect


REVISION = "d0a1b2c3e4f6"
DOWN_REVISION = "d0f1a2b3c4d5"
HEAD_REVISION = "ab02c3d4e5f6"
MIGRATION_PATH = Path(
    "alembic/versions/d0a1b2c3e4f6_add_tenant_offers_and_audit.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "tenant_offer_foundation_migration",
        MIGRATION_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_parent_schema(connection) -> None:
    metadata = sa.MetaData()
    sa.Table(
        "tenant",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
    )
    sa.Table(
        "storefront",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, nullable=False),
        sa.UniqueConstraint("id", "tenant_id", name="uq_storefront_id_tenant"),
    )
    sa.Table(
        "product",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
    )
    metadata.create_all(connection)


def test_tenant_offer_foundation_precedes_the_catalog_revision_head():
    script = ScriptDirectory.from_config(Config("alembic.ini"))

    assert script.get_heads() == ["f3a4b5c6d7e8"]
    assert script.get_revision("f2a3b4c5d6e7").down_revision == HEAD_REVISION
    assert script.get_revision(HEAD_REVISION).down_revision == "aa91c2d4e6f8"
    assert script.get_revision("aa91c2d4e6f8").down_revision == "e1f2a3b4c5d6"
    assert script.get_revision(REVISION).down_revision == DOWN_REVISION
    assert script.get_revision("e1f2a3b4c5d6").down_revision == REVISION


def test_tenant_offer_foundation_migration_is_additive_and_reversible():
    migration = _load_migration_module()
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        _create_parent_schema(connection)
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        inspector = inspect(connection)
        assert {"tenant_offer", "tenant_audit_event"}.issubset(
            inspector.get_table_names()
        )
        offer_columns = {
            column["name"]: column for column in inspector.get_columns("tenant_offer")
        }
        assert offer_columns["tenant_id"]["nullable"] is False
        assert offer_columns["storefront_id"]["nullable"] is False
        assert offer_columns["product_id"]["nullable"] is False
        assert offer_columns["price"]["nullable"] is False
        offer_indexes = {
            index["name"] for index in inspector.get_indexes("tenant_offer")
        }
        assert "ix_tenant_offer_scope_visibility" in offer_indexes
        offer_uniques = {
            constraint["name"]: tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("tenant_offer")
        }
        assert offer_uniques["uq_tenant_offer_scope_product"] == (
            "tenant_id",
            "storefront_id",
            "product_id",
        )
        offer_foreign_keys = {
            constraint["name"]: tuple(constraint["constrained_columns"])
            for constraint in inspector.get_foreign_keys("tenant_offer")
            if constraint["name"]
        }
        assert offer_foreign_keys["fk_tenant_offer_storefront_tenant"] == (
            "storefront_id",
            "tenant_id",
        )

        audit_columns = {
            column["name"]: column
            for column in inspector.get_columns("tenant_audit_event")
        }
        assert audit_columns["change_set"]["nullable"] is False
        assert audit_columns["request_id"]["nullable"] is False
        audit_foreign_keys = {
            constraint["name"]: tuple(constraint["constrained_columns"])
            for constraint in inspector.get_foreign_keys("tenant_audit_event")
            if constraint["name"]
        }
        assert audit_foreign_keys["fk_tenant_audit_storefront_tenant"] == (
            "storefront_id",
            "tenant_id",
        )

        migration.downgrade()
        assert "tenant_offer" not in inspect(connection).get_table_names()
        assert "tenant_audit_event" not in inspect(connection).get_table_names()
