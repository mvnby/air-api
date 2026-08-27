from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from tests.unit.alembic_chain_test_support import assert_revision_in_single_head_chain


REVISION = "e5f6a7b8c9d0"
HEAD_REVISION = "e7a8b9c0d1e2"


def _migration():
    path = Path("alembic/versions/e5f6a7b8c9d0_add_installation_discount_policy.py")
    spec = importlib.util.spec_from_file_location(
        "installation_discount_policy_migration",
        path,
    )
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_installation_discount_policy_is_the_single_alembic_head() -> None:
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert assert_revision_in_single_head_chain(scripts, REVISION) == HEAD_REVISION


def test_upgrade_seeds_disabled_policy_from_legacy_discount_and_is_reversible() -> None:
    engine = create_engine("sqlite:///:memory:")
    connection = engine.connect()
    connection.execute(
        text(
            "CREATE TABLE global_config ("
            "id INTEGER PRIMARY KEY, key VARCHAR NOT NULL UNIQUE, value VARCHAR NOT NULL)"
        )
    )
    connection.execute(
        text("CREATE TABLE product (id INTEGER PRIMARY KEY, title VARCHAR NOT NULL)")
    )
    connection.execute(
        text(
            "INSERT INTO global_config (id, key, value) "
            "VALUES (1, 'install_discount', '150')"
        )
    )
    migration = _migration()

    try:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        policy = connection.execute(
            text(
                "SELECT id, is_enabled, default_discount, minimum_margin "
                "FROM installation_discount_policy"
            )
        ).one()
        assert tuple(policy) == (1, 0, 150, 350)

        connection.execute(
            text(
                "INSERT INTO installation_discount_product_rule "
                "(product_id, discount_amount) VALUES (1, 0)"
            )
        )
        assert (
            connection.execute(
                text(
                    "SELECT discount_amount FROM installation_discount_product_rule "
                    "WHERE product_id = 1"
                )
            ).scalar_one()
            == 0
        )

        migration.downgrade()
        table_names = inspect(connection).get_table_names()
        assert "installation_discount_policy" not in table_names
        assert "installation_discount_product_rule" not in table_names
    finally:
        connection.close()
        engine.dispose()


def test_upgrade_falls_back_safely_for_invalid_legacy_discount() -> None:
    engine = create_engine("sqlite:///:memory:")
    connection = engine.connect()
    connection.execute(
        text(
            "CREATE TABLE global_config ("
            "id INTEGER PRIMARY KEY, key VARCHAR NOT NULL UNIQUE, value VARCHAR NOT NULL)"
        )
    )
    connection.execute(text("CREATE TABLE product (id INTEGER PRIMARY KEY)"))
    connection.execute(
        text(
            "INSERT INTO global_config (id, key, value) "
            "VALUES (1, 'install_discount', 'not-a-number')"
        )
    )
    migration = _migration()

    try:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert (
            connection.execute(
                text(
                    "SELECT default_discount FROM installation_discount_policy "
                    "WHERE id = 1"
                )
            ).scalar_one()
            == 0
        )
    finally:
        connection.close()
        engine.dispose()
