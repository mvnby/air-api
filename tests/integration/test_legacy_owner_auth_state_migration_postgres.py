from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text


def _load_migration():
    path = Path("alembic/versions/d2b3c4d5e6f7_add_legacy_owner_auth_state.py")
    spec = importlib.util.spec_from_file_location(
        "legacy_owner_auth_state_postgres_migration",
        path,
    )
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


@pytest.mark.asyncio
async def test_postgresql_upgrade_seed_guarded_downgrade_and_clean_downgrade(
    db_engine,
) -> None:
    schema = "legacy_owner_migration_contract"
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.execute(
                text(f'SET LOCAL search_path TO "{schema}"')
            )
            await connection.execute(
                text("CREATE TABLE staff_users (id INTEGER PRIMARY KEY)")
            )

            def upgrade(sync_connection) -> None:
                migration = _load_migration()
                migration.op = Operations(MigrationContext.configure(sync_connection))
                migration.upgrade()

            await connection.run_sync(upgrade)
            seeded = (
                await connection.execute(
                    text(
                        "SELECT id, mode, legacy_token_version, owner_staff_user_id "
                        "FROM legacy_owner_auth_state"
                    )
                )
            ).one()
            assert tuple(seeded) == (1, "legacy", 1, None)

            await connection.execute(text("INSERT INTO staff_users (id) VALUES (7)"))
            await connection.execute(
                text(
                    "UPDATE legacy_owner_auth_state SET "
                    "mode='staff_shadow', owner_staff_user_id=7, "
                    "legacy_token_version=2 WHERE id=1"
                )
            )

            def guarded_downgrade(sync_connection) -> None:
                migration = _load_migration()
                migration.op = Operations(MigrationContext.configure(sync_connection))
                with pytest.raises(RuntimeError, match="Refusing downgrade"):
                    migration.downgrade()

            await connection.run_sync(guarded_downgrade)
            assert await connection.scalar(
                text("SELECT to_regclass('legacy_owner_auth_state') IS NOT NULL")
            )

            await connection.execute(
                text(
                    "UPDATE legacy_owner_auth_state SET "
                    "mode='legacy', owner_staff_user_id=NULL WHERE id=1"
                )
            )

            def clean_downgrade(sync_connection) -> None:
                migration = _load_migration()
                migration.op = Operations(MigrationContext.configure(sync_connection))
                migration.downgrade()

            await connection.run_sync(clean_downgrade)
            assert not await connection.scalar(
                text("SELECT to_regclass('legacy_owner_auth_state') IS NOT NULL")
            )
        finally:
            await transaction.rollback()
