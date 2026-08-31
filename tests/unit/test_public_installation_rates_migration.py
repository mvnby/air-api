from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

from tests.unit.alembic_chain_test_support import assert_revision_in_single_head_chain


HEAD_REVISION = "f9a0b1c2d3e4"


def _migration():
    path = Path(
        "alembic/versions/d4e5f6a7b8c9_correct_public_installation_quote_rates.py"
    )
    spec = importlib.util.spec_from_file_location(
        "public_installation_rates_migration", path
    )
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_public_installation_rate_correction_is_the_single_alembic_head() -> None:
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert (
        assert_revision_in_single_head_chain(scripts, "d4e5f6a7b8c9") == HEAD_REVISION
    )


def test_public_installation_rate_correction_is_guarded_and_reversible() -> None:
    engine = create_engine("sqlite:///:memory:")
    connection = engine.connect()
    connection.execute(
        text(
            """
            CREATE TABLE installation_rates (
                id INTEGER PRIMARY KEY,
                category VARCHAR NOT NULL,
                power_range VARCHAR NOT NULL,
                base_price INTEGER NOT NULL
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO installation_rates (id, category, power_range, base_price) VALUES
                (1, 'Cassette', 'All', 1200),
                (2, 'Ceiling', 'All', 1200),
                (3, 'Cassette', '07-12', 1200),
                (4, 'Cassette', 'All', 1300),
                (5, 'Duct', 'All', 1500)
            """
        )
    )
    migration = _migration()
    try:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        rows = dict(
            connection.execute(
                text("SELECT id, base_price FROM installation_rates")
            ).all()
        )
        assert rows == {1: 1500, 2: 1400, 3: 1200, 4: 1300, 5: 1500}

        migration.downgrade()
        rows = dict(
            connection.execute(
                text("SELECT id, base_price FROM installation_rates")
            ).all()
        )
        assert rows == {1: 1200, 2: 1200, 3: 1200, 4: 1300, 5: 1500}
    finally:
        connection.close()
        engine.dispose()
