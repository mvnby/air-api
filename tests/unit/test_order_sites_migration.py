"""Order-site migration adds scoped links without rewriting legacy orders."""

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from tests.unit.alembic_chain_test_support import assert_revision_in_single_head_chain


REVISION = "order1278sites01"


def test_order_sites_migration_and_scoped_equipment_constraints():
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert_revision_in_single_head_chain(scripts, REVISION)
    migration = scripts.get_revision(REVISION).module

    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys=ON"))
            connection.execute(text('CREATE TABLE "order" (id INTEGER PRIMARY KEY, customer_branch_id INTEGER)'))
            connection.execute(text("CREATE TABLE customer (id INTEGER PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE customer_branches (id INTEGER PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE customer_equipment (id INTEGER PRIMARY KEY)"))
            connection.execute(text("INSERT INTO customer VALUES (1)"))
            connection.execute(text("INSERT INTO customer_branches VALUES (4)"))
            connection.execute(text('INSERT INTO "order" VALUES (1, 4), (2, NULL)'))
            connection.execute(text("INSERT INTO customer_equipment VALUES (1)"))

            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
            assert connection.execute(text('SELECT customer_branch_id FROM "order" WHERE id = 1')).scalar_one() == 4
            assert connection.execute(text("SELECT count(*) FROM order_site")).scalar_one() == 0
            connection.execute(text("""
                INSERT INTO order_site
                    (id, order_id, customer_id, customer_branch_id, title, address, version, created_at)
                VALUES (1, 1, 1, 4, 'Original', 'Original address', 1, CURRENT_TIMESTAMP),
                       (2, 1, 1, NULL, 'Extra', 'Extra address', 1, CURRENT_TIMESTAMP)
            """))
            insert_unit = text("""
                INSERT INTO order_site_equipment (order_id, site_id, equipment_id, role, created_at)
                VALUES (:order_id, :site_id, 1, 'diagnostic', CURRENT_TIMESTAMP)
            """)
            with pytest.raises(IntegrityError):
                connection.execute(insert_unit, {"order_id": 2, "site_id": 1})
            connection.execute(insert_unit, {"order_id": 1, "site_id": 1})
            with pytest.raises(IntegrityError):
                connection.execute(insert_unit, {"order_id": 1, "site_id": 2})

            connection.execute(text("DELETE FROM customer_branches WHERE id = 4"))
            assert connection.execute(text(
                "SELECT customer_branch_id, address FROM order_site WHERE id = 1"
            )).one() == (None, "Original address")
            connection.execute(text('DELETE FROM "order" WHERE id = 1'))
            assert connection.execute(text("SELECT count(*) FROM order_site")).scalar_one() == 0
            assert connection.execute(text("SELECT count(*) FROM order_site_equipment")).scalar_one() == 0

            with Operations.context(MigrationContext.configure(connection)):
                migration.downgrade()
            assert "order_site" not in inspect(connection).get_table_names()
            assert connection.execute(text('SELECT id FROM "order"')).scalar_one() == 2
    finally:
        engine.dispose()
