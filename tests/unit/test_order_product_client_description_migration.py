import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_description_upgrade_preserves_existing_product_identity_and_money():
    path = Path("alembic/versions/d43f9a0c6e84_add_order_product_client_description.py")
    spec = importlib.util.spec_from_file_location("product_description_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE order_product_link (id INTEGER PRIMARY KEY, product_id INTEGER, title_snapshot TEXT, quantity INTEGER, price INTEGER)"))
        connection.execute(text("INSERT INTO order_product_link VALUES (1, 42, 'Catalog model', 2, 2400)"))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        row = connection.execute(text("SELECT * FROM order_product_link")).mappings().one()
        assert dict(row) == dict(id=1, product_id=42, title_snapshot="Catalog model", quantity=2, price=2400, client_description=None)
        description = next(column for column in inspect(connection).get_columns("order_product_link") if column["name"] == "client_description")
        assert description["nullable"] is True
    engine.dispose()
