import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect


def _load_migration():
    path = Path("alembic/versions/8a3c5e7f9b21_add_bot_runtime_lease.py")
    spec = importlib.util.spec_from_file_location("bot_runtime_lease_migration", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_bot_runtime_lease_migration_replays_and_downgrades_on_sqlite(tmp_path, monkeypatch):
    migration = _load_migration()
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        monkeypatch.setattr(migration, "op", operations)

        migration.upgrade()
        migration.upgrade()
        inspector = inspect(connection)
        assert "bot_runtime_lease" in inspector.get_table_names()
        assert {index["name"] for index in inspector.get_indexes("bot_runtime_lease")} == {
            "ix_bot_runtime_lease_owner_id",
            "ix_bot_runtime_lease_expires_at",
            "ix_bot_runtime_lease_updated_at",
        }

        migration.downgrade()
        assert "bot_runtime_lease" not in inspect(connection).get_table_names()
