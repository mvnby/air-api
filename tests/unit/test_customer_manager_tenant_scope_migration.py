import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

from tests.unit.alembic_chain_test_support import (
    assert_revision_in_single_head_chain,
)


REVISION = "b8d9e0f1a2c3"
CONTRACT_REVISION = "c9e0f1a2b3d4"
STOREFRONT_IDEMPOTENCY_REVISION = "d0f1a2b3c4d5"
TENANT_OFFER_REVISION = "d0a1b2c3e4f6"
PREVIOUS_HEAD_REVISION = "f5c6d7e8a9b0"
WEBSITE_CANARY_REVISION = "ab02c3d4e5f6"
PUBLIC_WRITE_REVISION = "aa91c2d4e6f8"
CATALOG_REVISION = "e1f2a3b4c5d6"
MIGRATION_PATH = Path(
    "alembic/versions/b8d9e0f1a2c3_add_customer_manager_tenant_scope.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "customer_manager_tenant_scope_migration",
        MIGRATION_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_legacy_schema(connection) -> None:
    metadata = sa.MetaData()
    sa.Table(
        "tenant",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("slug", sa.String, nullable=False),
        sa.Column("is_system", sa.Boolean, nullable=False),
    )
    sa.Table(
        "staff_users",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("primary_role", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
    )
    sa.Table(
        "tenant_membership",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, nullable=False),
        sa.Column("staff_user_id", sa.Integer, nullable=False),
        sa.Column("role", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "staff_user_id"),
    )
    sa.Table(
        "customer",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("phone", sa.String),
        sa.Column("inn", sa.String),
        sa.Column("created_at", sa.DateTime),
    )
    sa.Table(
        "customer_requisites_recognition",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
    )
    metadata.create_all(connection)
    connection.execute(
        sa.text(
            "INSERT INTO tenant (id, slug, is_system) "
            "VALUES (1, 'mvn', 1)"
        )
    )
    connection.execute(
        sa.text(
            "INSERT INTO staff_users (id, primary_role, status) "
            "VALUES (10, 'manager', 'active')"
        )
    )


def test_customer_manager_tenant_scope_is_single_alembic_head():
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    assert_revision_in_single_head_chain(script, REVISION)
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
    assert script.get_revision(CONTRACT_REVISION).down_revision == REVISION


def test_customer_manager_tenant_scope_migration_is_additive_and_guarded():
    migration = _load_migration_module()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        _create_legacy_schema(connection)
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        inspector = sa.inspect(connection)
        assert "tenant_id" in {
            column["name"]
            for column in inspector.get_columns("customer")
        }
        assert "tenant_id" in {
            column["name"]
            for column in inspector.get_columns(
                "customer_requisites_recognition"
            )
        }
        assert connection.execute(
            sa.text(
                "SELECT COUNT(*) FROM tenant_membership "
                "WHERE tenant_id = 1 AND staff_user_id = 10 "
                "AND role = 'manager' AND status = 'active'"
            )
        ).scalar_one() == 1

        connection.execute(
            sa.text(
                "INSERT INTO customer "
                "(id, phone, created_at, tenant_id) "
                "VALUES (1, '+375290000001', CURRENT_TIMESTAMP, 1)"
            )
        )
        with pytest.raises(RuntimeError, match="scoped customer rows"):
            migration.downgrade()

        connection.execute(
            sa.text("UPDATE customer SET tenant_id = NULL")
        )
        migration.downgrade()
        inspector = sa.inspect(connection)
        assert "tenant_id" not in {
            column["name"]
            for column in inspector.get_columns("customer")
        }
