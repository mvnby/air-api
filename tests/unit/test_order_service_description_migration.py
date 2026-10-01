import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_nullable_description_migration_preserves_existing_rows_and_downgrades(monkeypatch):
    path = Path(__file__).parents[2] / "alembic/versions/fb1c2d3e4f5a_order_service_description.py"
    spec = importlib.util.spec_from_file_location("service_description_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE order_service_link (id INTEGER PRIMARY KEY, title TEXT)"))
            connection.execute(text("INSERT INTO order_service_link (id, title) VALUES (1, 'Existing')"))
            monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
            migration.upgrade()
            assert connection.execute(text("SELECT title, description FROM order_service_link WHERE id=1")).one() == ("Existing", None)
            connection.execute(text("UPDATE order_service_link SET description='Reviewed scope' WHERE id=1"))
            assert next(column for column in inspect(connection).get_columns("order_service_link")
                        if column["name"] == "description")["nullable"]
            migration.downgrade()
            assert [column["name"] for column in inspect(connection).get_columns("order_service_link")] == ["id", "title"]
    finally:
        engine.dispose()
