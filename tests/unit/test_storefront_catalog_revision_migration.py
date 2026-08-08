import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import inspect


REVISION = "e1f2a3b4c5d6"
DOWN_REVISION = "d0a1b2c3e4f6"
HEAD_REVISION = "f2a3b4c5d6e7"
MIGRATION_PATH = Path(
    "alembic/versions/e1f2a3b4c5d6_add_storefront_catalog_revision.py"
)
CLAIM_INDEX = "ix_integration_outbox_event_catalog_claim"


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "storefront_catalog_revision_migration",
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
        "integration_outbox_event",
        metadata,
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("priority", sa.Integer, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(connection)


def test_storefront_catalog_revision_is_the_single_alembic_head():
    script = ScriptDirectory.from_config(Config("alembic.ini"))

    assert script.get_heads() == [HEAD_REVISION]
    assert script.get_revision(HEAD_REVISION).down_revision == "ab02c3d4e5f6"
    assert script.get_revision("ab02c3d4e5f6").down_revision == "aa91c2d4e6f8"
    assert script.get_revision("aa91c2d4e6f8").down_revision == REVISION
    assert script.get_revision(REVISION).down_revision == DOWN_REVISION


def test_storefront_catalog_revision_migration_is_additive_and_reversible():
    migration = _load_migration_module()
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        _create_parent_schema(connection)
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        inspector = inspect(connection)
        assert "storefront_catalog_revision" in inspector.get_table_names()
        columns = {
            column["name"]: column
            for column in inspector.get_columns("storefront_catalog_revision")
        }
        assert columns["tenant_id"]["nullable"] is False
        assert columns["storefront_id"]["nullable"] is False
        assert columns["revision"]["nullable"] is False
        assert columns["updated_at"]["nullable"] is False
        primary_key = inspector.get_pk_constraint(
            "storefront_catalog_revision"
        )
        assert tuple(primary_key["constrained_columns"]) == (
            "tenant_id",
            "storefront_id",
        )
        foreign_keys = {
            constraint["name"]: tuple(constraint["constrained_columns"])
            for constraint in inspector.get_foreign_keys(
                "storefront_catalog_revision"
            )
            if constraint["name"]
        }
        assert foreign_keys[
            "fk_storefront_catalog_revision_storefront_tenant"
        ] == ("storefront_id", "tenant_id")
        check_names = {
            constraint["name"]
            for constraint in inspector.get_check_constraints(
                "storefront_catalog_revision"
            )
        }
        assert "ck_storefront_catalog_revision_non_negative" in check_names
        outbox_indexes = {
            index["name"]: tuple(index["column_names"])
            for index in inspector.get_indexes("integration_outbox_event")
        }
        assert outbox_indexes[CLAIM_INDEX] == (
            "event_type",
            "status",
            "available_at",
            "priority",
            "occurred_at",
        )

        migration.downgrade()
        inspector = inspect(connection)
        assert "storefront_catalog_revision" not in inspector.get_table_names()
        assert CLAIM_INDEX not in {
            index["name"]
            for index in inspector.get_indexes("integration_outbox_event")
        }
