"""The additive use timestamp preserves every existing grant and permission."""

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import Column, DateTime, Integer, JSON, MetaData, Table, create_engine, inspect, select

from tests.unit.alembic_chain_test_support import assert_revision_in_single_head_chain


def test_last_used_migration_is_in_single_head_chain():
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert_revision_in_single_head_chain(scripts, "t1152conn01")


def test_last_used_migration_preserves_existing_grants():
    path = Path("alembic/versions/t1152conn01_add_connector_last_used_at.py")
    spec = importlib.util.spec_from_file_location("connector_last_used_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    metadata = MetaData()
    grants = Table("connector_grant", metadata,
                   Column("id", Integer, primary_key=True),
                   Column("scopes", JSON, nullable=False),
                   Column("revoked_at", DateTime, nullable=True))
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(grants.insert(), [{"id": 1, "scopes": ["kitlane:read", "kitlane:mail:send"]}])
        before = connection.execute(select(grants)).mappings().all()
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        reflected = Table("connector_grant", MetaData(), autoload_with=connection)
        assert reflected.c.last_used_at.nullable
        assert connection.execute(select(reflected.c.last_used_at)).scalar_one() is None
        assert connection.execute(select(grants)).mappings().all() == before
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert "last_used_at" not in {column["name"] for column in inspect(connection).get_columns("connector_grant")}
        assert connection.execute(select(grants)).mappings().all() == before
