"""Execute the additive migration and immutable guards on physical PostgreSQL."""
import importlib.util
from pathlib import Path
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


@pytest.mark.asyncio
async def test_additive_migration_immutable_evidence_and_safe_downgrade(db_engine):
    path = Path('alembic/versions/f13d5e6f7081_add_maintenance_offers.py')
    spec = importlib.util.spec_from_file_location('maintenance_offer_migration', path)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.execute(text('CREATE SCHEMA maintenance_offer_migration_test'))
            await connection.execute(text('SET LOCAL search_path TO maintenance_offer_migration_test'))
            for table in ('maintenance_continuation', 'order_proposal', 'maintenance_observation_revision', 'maintenance_observation', 'equipment_service_history'):
                await connection.execute(text(f'CREATE TABLE {table} (id INTEGER PRIMARY KEY)'))
                await connection.execute(text(f'INSERT INTO {table} VALUES (1)'))
            await connection.execute(text('CREATE TABLE "order" (id INTEGER PRIMARY KEY, title TEXT)'))
            await connection.execute(text("INSERT INTO \"order\" VALUES (1, 'historical TO')"))
            def upgrade(sync):
                migration.op = Operations(MigrationContext.configure(sync)); migration.upgrade()
            await connection.run_sync(upgrade)
            assert (await connection.execute(text('SELECT title FROM "order"'))).scalar() == 'historical TO'
            savepoint = await connection.begin_nested()
            await connection.execute(text("INSERT INTO maintenance_offer VALUES (1, 1, 1, 'key', 'hash', '{}', 'manager', now())"))
            with pytest.raises(RuntimeError, match='Export'):
                await connection.run_sync(lambda sync: migration.downgrade())
            for sql in ["UPDATE maintenance_offer SET snapshot = '{\"changed\": true}' WHERE id = 1", 'DELETE FROM maintenance_offer WHERE id = 1']:
                inner = await connection.begin_nested()
                with pytest.raises(IntegrityError, match='immutable'):
                    await connection.execute(text(sql))
                await inner.rollback()
            await savepoint.rollback()
            await connection.run_sync(lambda sync: migration.downgrade())
            assert (await connection.execute(text('SELECT title FROM "order"'))).scalar() == 'historical TO'
        finally:
            await transaction.rollback()
