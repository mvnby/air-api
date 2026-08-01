import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlmodel import SQLModel

import models  # noqa: F401 - register SQLModel metadata


REVISION = "c9e0f1a2b3d4"
MIGRATION_PATH = Path(
    "alembic/versions/c9e0f1a2b3d4_contract_tenant_provenance.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "tenant_provenance_contract_migration",
        MIGRATION_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_expand_schema(connection, *, include_null_order: bool = False) -> None:
    metadata = sa.MetaData()
    tenant = sa.Table(
        "tenant",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
    )
    storefront = sa.Table(
        "storefront",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey(tenant.c.id), nullable=False),
    )
    customer = sa.Table(
        "customer",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey(tenant.c.id), nullable=True),
    )
    order = sa.Table(
        "order",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey(tenant.c.id), nullable=True),
        sa.Column("storefront_id", sa.Integer, nullable=True),
        sa.Column("customer_id", sa.Integer, nullable=True),
        sa.Column("source_fingerprint", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(
            ["storefront_id"],
            [storefront.c.id],
            name="fk_order_storefront_id_storefront",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            [customer.c.id],
            name="fk_order_customer_id_customer",
        ),
    )
    lead = sa.Table(
        "lead",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey(tenant.c.id), nullable=True),
        sa.Column("storefront_id", sa.Integer, nullable=True),
        sa.Column("converted_order_id", sa.Integer, nullable=True),
        sa.Column("source", sa.String(24), nullable=False),
        sa.Column("source_fingerprint", sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(
            ["storefront_id"],
            [storefront.c.id],
            name="fk_lead_storefront_id_storefront",
        ),
        sa.ForeignKeyConstraint(
            ["converted_order_id"],
            [order.c.id],
            name="fk_lead_converted_order_id_order",
        ),
    )
    recognition = sa.Table(
        "customer_requisites_recognition",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey(tenant.c.id), nullable=True),
        sa.Column("source", sa.String(24), nullable=False),
        sa.Column("telegram_user_id", sa.Integer, nullable=True),
        sa.Column("telegram_chat_id", sa.Integer, nullable=True),
        sa.Column("telegram_message_id", sa.Integer, nullable=True),
        sa.Column("duplicate_customer_id", sa.Integer, nullable=True),
        sa.Column("confirmed_customer_id", sa.Integer, nullable=True),
        sa.ForeignKeyConstraint(
            ["duplicate_customer_id"],
            [customer.c.id],
            name="fk_customer_requisites_duplicate_customer_id",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_customer_id"],
            [customer.c.id],
            name="fk_customer_requisites_confirmed_customer_id",
        ),
    )
    sa.Index(
        "uq_order_source_fingerprint",
        order.c.source_fingerprint,
        unique=True,
        sqlite_where=text("source_fingerprint IS NOT NULL"),
    )
    sa.Index(
        "uq_lead_bot_source_fingerprint",
        lead.c.source_fingerprint,
        unique=True,
        sqlite_where=text(
            "source = 'bot' AND source_fingerprint IS NOT NULL"
        ),
    )
    sa.Index(
        "uq_customer_requisites_telegram_message",
        recognition.c.source,
        recognition.c.telegram_user_id,
        recognition.c.telegram_chat_id,
        recognition.c.telegram_message_id,
        unique=True,
        sqlite_where=text(
            "source IN ('telegram', 'telegram_text') "
            "AND telegram_user_id IS NOT NULL "
            "AND telegram_chat_id IS NOT NULL "
            "AND telegram_message_id IS NOT NULL"
        ),
    )
    metadata.create_all(connection)

    connection.execute(tenant.insert().values(id=1))
    connection.execute(storefront.insert().values(id=1, tenant_id=1))
    connection.execute(customer.insert().values(id=1, tenant_id=1))
    connection.execute(
        order.insert().values(
            id=1,
            tenant_id=None if include_null_order else 1,
            storefront_id=None if include_null_order else 1,
            customer_id=1,
            source_fingerprint="shared-order-key",
        )
    )
    if not include_null_order:
        connection.execute(
            lead.insert().values(
                id=1,
                tenant_id=1,
                storefront_id=1,
                converted_order_id=1,
                source="bot",
                source_fingerprint="shared-lead-key",
            )
        )
        connection.execute(
            recognition.insert().values(
                id=1,
                tenant_id=1,
                source="telegram",
                telegram_user_id=10,
                telegram_chat_id=20,
                telegram_message_id=30,
                duplicate_customer_id=1,
                confirmed_customer_id=1,
            )
        )


def _migration_engine(*, include_null_order: bool = False):
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys = ON"))
        _create_expand_schema(
            connection,
            include_null_order=include_null_order,
        )
    return engine


def _run_migration(engine, action: str) -> None:
    migration = _load_migration_module()
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
        connection.commit()
        with connection.begin():
            migration.op = Operations(MigrationContext.configure(connection))
            getattr(migration, action)()
        connection.exec_driver_sql("PRAGMA foreign_keys = ON")
        connection.commit()


def test_tenant_provenance_contract_is_the_single_alembic_head():
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = script.get_revision(REVISION)

    assert script.get_heads() == ["ab02c3d4e5f6"]
    assert revision is not None
    assert revision.down_revision == "b8d9e0f1a2c3"


def test_contract_upgrade_requires_clean_backfill():
    engine = _migration_engine(include_null_order=True)

    with pytest.raises(
        RuntimeError,
        match="order_null_scope=1",
    ):
        _run_migration(engine, "upgrade")

    columns = {
        column["name"]: column
        for column in inspect(engine).get_columns("order")
    }
    assert columns["tenant_id"]["nullable"] is True
    assert columns["storefront_id"]["nullable"] is True


def test_contract_upgrade_enforces_scope_and_tenant_local_idempotency():
    engine = _migration_engine()
    _run_migration(engine, "upgrade")

    inspector = inspect(engine)
    for table_name, column_names in (
        ("customer", ("tenant_id",)),
        ("customer_requisites_recognition", ("tenant_id",)),
        ("lead", ("tenant_id", "storefront_id")),
        ("order", ("tenant_id", "storefront_id")),
    ):
        columns = {
            column["name"]: column
            for column in inspector.get_columns(table_name)
        }
        assert all(columns[name]["nullable"] is False for name in column_names)

    assert {
        index["name"]: index["column_names"]
        for index in inspector.get_indexes("lead")
    }["uq_lead_bot_source_fingerprint"] == [
        "tenant_id",
        "source_fingerprint",
    ]
    assert {
        index["name"]: index["column_names"]
        for index in inspector.get_indexes("order")
    }["uq_order_source_fingerprint"] == [
        "tenant_id",
        "source_fingerprint",
    ]

    foreign_keys = {
        foreign_key["name"]: tuple(foreign_key["constrained_columns"])
        for foreign_key in inspector.get_foreign_keys("order")
    }
    assert foreign_keys["fk_order_storefront_tenant"] == (
        "storefront_id",
        "tenant_id",
    )
    assert foreign_keys["fk_order_customer_tenant"] == (
        "customer_id",
        "tenant_id",
    )

    with engine.begin() as connection:
        connection.execute(text("INSERT INTO tenant (id) VALUES (2)"))
        connection.execute(
            text("INSERT INTO storefront (id, tenant_id) VALUES (2, 2)")
        )
        connection.execute(
            text("INSERT INTO customer (id, tenant_id) VALUES (2, 2)")
        )
        connection.execute(
            text(
                'INSERT INTO "order" '
                "(id, tenant_id, storefront_id, customer_id, source_fingerprint) "
                "VALUES (2, 2, 2, 2, 'shared-order-key')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO lead "
                "(id, tenant_id, storefront_id, converted_order_id, source, "
                "source_fingerprint) "
                "VALUES (2, 2, 2, 2, 'bot', 'shared-lead-key')"
            )
        )

    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    'INSERT INTO "order" '
                    "(id, tenant_id, storefront_id, customer_id) "
                    "VALUES (3, 2, 1, 2)"
                )
            )
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    'INSERT INTO "order" '
                    "(id, tenant_id, storefront_id, customer_id) "
                    "VALUES (3, 2, 2, 1)"
                )
            )

    with pytest.raises(RuntimeError, match="cross_tenant_order_fingerprint"):
        _run_migration(engine, "downgrade")


def test_contract_model_metadata_matches_database_boundary():
    expected_not_null = {
        "customer": ("tenant_id",),
        "customer_requisites_recognition": ("tenant_id",),
        "lead": ("tenant_id", "storefront_id"),
        "order": ("tenant_id", "storefront_id"),
    }
    for table_name, columns in expected_not_null.items():
        table = SQLModel.metadata.tables[table_name]
        assert all(table.c[column].nullable is False for column in columns)
        assert all(table.c[column].server_default is None for column in columns)

    order_indexes = {
        index.name: tuple(column.name for column in index.columns)
        for index in SQLModel.metadata.tables["order"].indexes
    }
    lead_indexes = {
        index.name: tuple(column.name for column in index.columns)
        for index in SQLModel.metadata.tables["lead"].indexes
    }
    assert order_indexes["uq_order_source_fingerprint"] == (
        "tenant_id",
        "storefront_id",
        "source_fingerprint",
    )
    assert lead_indexes["uq_lead_bot_source_fingerprint"] == (
        "tenant_id",
        "source_fingerprint",
    )
