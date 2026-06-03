import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Boolean, Column, Float, Integer, MetaData, String, Table, create_engine, text


def test_staff_users_migration_backfills_existing_installers(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    metadata = MetaData()
    installers = Table(
        "installers",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String, nullable=False),
        Column("is_active", Boolean, nullable=False),
        Column("default_rate", Float),
        Column("telegram_id", Integer),
    )
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(
            installers.insert(),
            [
                {"id": 1, "name": "Active", "is_active": True, "default_rate": 100, "telegram_id": 101},
                {"id": 2, "name": "Inactive", "is_active": False, "default_rate": None, "telegram_id": None},
            ],
        )

        migration_path = Path("alembic/versions/7c8d9e0f1a23_add_staff_users_foundation.py")
        spec = importlib.util.spec_from_file_location("staff_users_migration", migration_path)
        assert spec and spec.loader
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        context = MigrationContext.configure(conn)
        monkeypatch.setattr(migration, "op", Operations(context))

        migration.upgrade()

        rows = conn.execute(text("SELECT * FROM staff_users ORDER BY id")).fetchall()

    assert len(rows) == 2
    by_name = {row._mapping["display_name"]: row._mapping for row in rows}
    assert by_name["Active"]["status"] == "active"
    assert by_name["Active"]["roles"] == '["installer"]'
    assert by_name["Active"]["legacy_installer_id"] == 1
    assert by_name["Inactive"]["status"] == "inactive"
