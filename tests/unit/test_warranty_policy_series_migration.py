import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from tests.unit.alembic_chain_test_support import assert_revision_in_single_head_chain


MIGRATION_PATH = Path("alembic/versions/e56b2c3d4e5_add_warranty_policy_series_links.py")
REVISION = "e56b2c3d4e5"


def _load_migration():
    spec = importlib.util.spec_from_file_location("warranty_policy_series_migration", MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_warranty_policy_series_migration_stays_in_the_single_head_chain():
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert_revision_in_single_head_chain(scripts, REVISION)
    assert scripts.get_revision(REVISION).down_revision == "e55b1c2d3e4f"


def test_warranty_policy_series_migration_upgrades_backfills_and_downgrades_sqlite():
    migration = _load_migration()
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as connection:
        metadata = sa.MetaData()
        sa.Table("brand", metadata, sa.Column("id", sa.Integer(), primary_key=True))
        sa.Table("supplier", metadata, sa.Column("id", sa.Integer(), primary_key=True))
        sa.Table("product", metadata, sa.Column("id", sa.Integer(), primary_key=True))
        sa.Table(
            "product_series",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brand.id")),
        )
        warranty_policy = sa.Table(
            "warranty_policy",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("series_id", sa.Integer(), sa.ForeignKey("product_series.id")),
        )
        metadata.create_all(connection)
        connection.execute(sa.insert(warranty_policy), [{"id": 1, "series_id": 11}, {"id": 2, "series_id": None}])

        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        links = connection.execute(
            sa.text("SELECT policy_id, series_id, sort_order FROM warranty_policy_series_link ORDER BY policy_id")
        ).all()
        assert links == [(1, 11, 0)]
        indexes = {index["name"] for index in inspect(connection).get_indexes("warranty_policy_series_link")}
        assert "ix_warranty_policy_series_link_series_policy" in indexes

        migration.downgrade()
        assert "warranty_policy_series_link" not in inspect(connection).get_table_names()
