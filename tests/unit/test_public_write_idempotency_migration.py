import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text


REVISION = "aa91c2d4e6f8"
MIGRATION_PATH = Path(
    "alembic/versions/aa91c2d4e6f8_add_public_write_idempotency.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "public_write_idempotency_migration",
        MIGRATION_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _engine():
    engine = sa.create_engine("sqlite://")
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
    metadata.create_all(engine)
    return engine


def _run(engine, action: str) -> None:
    migration = _load_migration_module()
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        getattr(migration, action)()


def test_public_write_idempotency_migration_is_single_head() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = script.get_revision(REVISION)

    assert script.get_heads() == [REVISION]
    assert revision is not None
    assert revision.down_revision == "d0a1b2c3e4f6"


def test_public_write_idempotency_upgrade_and_downgrade() -> None:
    engine = _engine()
    _run(engine, "upgrade")

    inspector = inspect(engine)
    assert "public_write_idempotency" in inspector.get_table_names()
    assert {
        constraint["name"] for constraint in inspector.get_unique_constraints(
            "public_write_idempotency"
        )
    } == {"uq_public_write_idempotency_scope_command_key"}
    assert {
        index["name"] for index in inspector.get_indexes(
            "public_write_idempotency"
        )
    } == {"ix_public_write_idempotency_scope_created_at"}

    insert_receipt = text(
        "INSERT INTO public_write_idempotency "
        "(tenant_id, storefront_id, command_name, key_hash, "
        "request_fingerprint, created_at) "
        "VALUES (:tenant_id, :storefront_id, :command_name, :key_hash, "
        ":request_fingerprint, CURRENT_TIMESTAMP)"
    )
    values = {
        "tenant_id": 1,
        "storefront_id": 1,
        "command_name": "public_contact_lead_v1",
        "key_hash": "a" * 64,
        "request_fingerprint": "b" * 64,
    }
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO tenant (id) VALUES (1)"))
        connection.execute(
            text(
                "INSERT INTO storefront (id, tenant_id) VALUES (1, 1), (2, 1)"
            )
        )
        connection.execute(insert_receipt, values)
        connection.execute(insert_receipt, {**values, "storefront_id": 2})

    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(insert_receipt, values)

    _run(engine, "downgrade")
    assert "public_write_idempotency" not in inspect(engine).get_table_names()
