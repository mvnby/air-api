import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, text

from tests.unit.alembic_chain_test_support import assert_revision_in_single_head_chain


REVISION = "c8d9e0f1a2b3"


def _load_migration():
    path = Path("alembic/versions/c8d9e0f1a2b3_add_staff_credential_version.py")
    spec = importlib.util.spec_from_file_location("staff_credential_state_migration", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_staff_credential_state_is_in_the_single_alembic_head_chain() -> None:
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert_revision_in_single_head_chain(scripts, REVISION)


def test_staff_credential_state_migration_upgrades_existing_rows_and_downgrades(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    metadata = MetaData()
    staff_users = Table(
        "staff_users",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("username", String, nullable=True),
        Column("password_hash", String, nullable=True),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            staff_users.insert(),
            {"id": 1, "username": "existing", "password_hash": "bcrypt-hash"},
        )
        migration = _load_migration()
        monkeypatch.setattr(
            migration,
            "op",
            Operations(MigrationContext.configure(connection)),
        )

        migration.upgrade()

        existing = connection.execute(
            text(
                "SELECT auth_version, password_changed_at, must_change_password "
                "FROM staff_users WHERE id = 1"
            )
        ).one()
        assert tuple(existing) == (1, None, 0)
        connection.execute(
            text("INSERT INTO staff_users (id, username) VALUES (2, 'new-user')")
        )
        created = connection.execute(
            text(
                "SELECT auth_version, must_change_password "
                "FROM staff_users WHERE id = 2"
            )
        ).one()
        assert tuple(created) == (1, 0)

        migration.downgrade()
        columns = {column["name"] for column in inspect(connection).get_columns("staff_users")}

    assert "auth_version" not in columns
    assert "password_changed_at" not in columns
    assert "must_change_password" not in columns
