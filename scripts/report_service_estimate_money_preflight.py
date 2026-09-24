"""Read-only preflight for the estimate money schema expansion."""

import importlib.util
from pathlib import Path
import sys

import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import settings


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic/versions/e68b7c9d0e1f_expand_estimate_money_precision.py"
)


def main() -> None:
    spec = importlib.util.spec_from_file_location("estimate_money_migration", MIGRATION)
    if spec is None or spec.loader is None:
        raise RuntimeError("Estimate money migration is missing")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    database_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg")
    engine = sa.create_engine(database_url)
    try:
        with engine.connect() as connection:
            with connection.begin():
                if connection.dialect.name == "postgresql":
                    connection.execute(sa.text("SET TRANSACTION READ ONLY"))
                migration._preflight_estimates(connection)
        print("estimate_money_preflight=passed")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
