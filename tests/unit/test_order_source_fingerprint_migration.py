import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect


REVISION = "f4d5e6f7a8b9"
MIGRATION_PATH = Path(
    "alembic/versions/f4d5e6f7a8b9_add_order_source_fingerprint.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "order_source_fingerprint_migration",
        MIGRATION_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_order_source_fingerprint_remains_in_the_single_alembic_chain():
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = script.get_revision(REVISION)

    assert script.get_heads() == ["d0a1b2c3e4f6"]
    assert revision is not None
    assert revision.down_revision == "f3c4d5e6f7a8"
    assert set(revision.nextrev) == {"d8e7f6a5b4c3"}


def test_order_source_fingerprint_migration_upgrades_and_downgrades_sqlite():
    migration = _load_migration_module()
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as connection:
        sa.Table(
            "order",
            sa.MetaData(),
            sa.Column("id", sa.Integer(), primary_key=True),
        ).create(connection)
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        inspector = inspect(connection)
        columns = {column["name"] for column in inspector.get_columns("order")}
        indexes = {index["name"]: index for index in inspector.get_indexes("order")}
        assert "source_fingerprint" in columns
        assert indexes["uq_order_source_fingerprint"]["unique"] == 1

        migration.downgrade()
        assert "source_fingerprint" not in {
            column["name"] for column in inspect(connection).get_columns("order")
        }
