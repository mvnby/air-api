import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from tests.unit.alembic_chain_test_support import assert_revision_in_single_head_chain


REVISION = "d1a2b3c4e5f6"


def _load_migration():
    path = Path("alembic/versions/d1a2b3c4e5f6_add_auth_login_throttle.py")
    spec = importlib.util.spec_from_file_location("auth_login_throttle_migration", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_auth_login_throttle_is_in_the_single_alembic_head_chain() -> None:
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert_revision_in_single_head_chain(scripts, REVISION)


def test_auth_login_throttle_migration_upgrades_and_downgrades(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as connection:
        migration = _load_migration()
        monkeypatch.setattr(
            migration,
            "op",
            Operations(MigrationContext.configure(connection)),
        )

        migration.upgrade()
        inspector = inspect(connection)
        columns = {
            column["name"]: column
            for column in inspector.get_columns("auth_login_throttle")
        }
        assert set(columns) == {
            "fingerprint",
            "failure_count",
            "window_started_at",
            "blocked_until",
            "updated_at",
        }
        assert columns["fingerprint"]["primary_key"] == 1
        assert {
            index["name"]
            for index in inspector.get_indexes("auth_login_throttle")
        } == {"ix_auth_login_throttle_updated_at"}

        migration.downgrade()
        assert "auth_login_throttle" not in inspect(connection).get_table_names()
