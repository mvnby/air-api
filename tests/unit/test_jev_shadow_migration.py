import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from models.jev_shadow import JevConnection, JevShadowSample
from tests.unit.alembic_chain_test_support import assert_revision_in_single_head_chain


def test_jev_migration_empty_and_model_contract_matches():
    assert_revision_in_single_head_chain(ScriptDirectory.from_config(Config("alembic.ini")), "fe34cd56ef78")
    spec = importlib.util.spec_from_file_location("jev_migration", Path("alembic/versions/fe34cd56ef78_add_jev_shadow.py"))
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()
        for model in [JevConnection, JevShadowSample]:
            table = model.__table__
            columns = inspect(conn).get_columns(table.name)
            assert {c["name"] for c in columns} == set(table.columns.keys())
            for column in columns:
                assert str(column["type"]) == str(table.columns[column["name"]].type.compile(dialect=conn.dialect))
            assert conn.execute(text(f"SELECT COUNT(*) FROM {table.name}")).scalar_one() == 0
        migration.downgrade()
        assert "jev_connection" not in inspect(conn).get_table_names()
    engine.dispose()
