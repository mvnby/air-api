import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text


REVISION = "d0f1a2b3c4d5"
MIGRATION_PATH = Path(
    "alembic/versions/d0f1a2b3c4d5_scope_order_fingerprint_to_storefront.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "storefront_order_idempotency_migration",
        MIGRATION_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _engine(*, nullable_scope: bool = False):
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    order = sa.Table(
        "order",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, nullable=nullable_scope),
        sa.Column("storefront_id", sa.Integer, nullable=nullable_scope),
        sa.Column("source_fingerprint", sa.String(64), nullable=True),
    )
    sa.Index(
        "uq_order_source_fingerprint",
        order.c.tenant_id,
        order.c.source_fingerprint,
        unique=True,
        sqlite_where=text("source_fingerprint IS NOT NULL"),
    )
    metadata.create_all(engine)
    return engine


def _run(engine, action: str) -> None:
    migration = _load_migration_module()
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        getattr(migration, action)()


def test_storefront_idempotency_migration_is_the_single_head():
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = script.get_revision(REVISION)

    assert script.get_heads() == ["ab02c3d4e5f6"]
    assert revision is not None
    assert revision.down_revision == "c9e0f1a2b3d4"


def test_upgrade_allows_same_key_across_storefronts_but_not_inside_one():
    engine = _engine()
    with engine.begin() as connection:
        connection.execute(
            text(
                'INSERT INTO "order" '
                "(id, tenant_id, storefront_id, source_fingerprint) "
                "VALUES (1, 1, 1, 'shared-key')"
            )
        )

    _run(engine, "upgrade")

    indexes = {
        index["name"]: index
        for index in inspect(engine).get_indexes("order")
    }
    assert indexes["uq_order_source_fingerprint"]["column_names"] == [
        "tenant_id",
        "storefront_id",
        "source_fingerprint",
    ]
    assert indexes["uq_order_source_fingerprint"]["unique"] == 1

    with engine.begin() as connection:
        connection.execute(
            text(
                'INSERT INTO "order" '
                "(id, tenant_id, storefront_id, source_fingerprint) "
                "VALUES (2, 1, 2, 'shared-key')"
            )
        )

    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    'INSERT INTO "order" '
                    "(id, tenant_id, storefront_id, source_fingerprint) "
                    "VALUES (3, 1, 2, 'shared-key')"
                )
            )

    with pytest.raises(
        RuntimeError,
        match="duplicate_tenant_order_fingerprint=1",
    ):
        _run(engine, "downgrade")


def test_upgrade_rejects_fingerprint_without_complete_provenance():
    engine = _engine(nullable_scope=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                'INSERT INTO "order" '
                "(id, tenant_id, storefront_id, source_fingerprint) "
                "VALUES (1, 1, NULL, 'unsafe-key')"
            )
        )

    with pytest.raises(
        RuntimeError,
        match="order_fingerprint_null_scope=1",
    ):
        _run(engine, "upgrade")


def test_downgrade_restores_tenant_scoped_index_when_lossless():
    engine = _engine()
    _run(engine, "upgrade")

    with engine.begin() as connection:
        connection.execute(
            text(
                'INSERT INTO "order" '
                "(id, tenant_id, storefront_id, source_fingerprint) "
                "VALUES (1, 1, 1, 'one-key'), (2, 1, 2, 'another-key')"
            )
        )

    _run(engine, "downgrade")

    indexes = {
        index["name"]: index
        for index in inspect(engine).get_indexes("order")
    }
    assert indexes["uq_order_source_fingerprint"]["column_names"] == [
        "tenant_id",
        "source_fingerprint",
    ]
