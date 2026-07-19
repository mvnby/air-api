import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text


REVISION = "a13c5e7f9b24"
MIGRATION_PATH = Path("alembic/versions/a13c5e7f9b24_add_tenant_storefront_foundation.py")


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("tenant_storefront_foundation_migration", MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tenant_storefront_foundation_is_in_the_single_alembic_head_chain():
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = script.get_revision(REVISION)
    heads = script.get_heads()

    assert len(heads) == 1
    assert REVISION in {item.revision for item in script.walk_revisions("base", heads[0])}
    assert revision is not None
    assert revision.down_revision == "9b4d6f8a1c30"


def test_tenant_storefront_foundation_migration_seeds_mvn_and_downgrades_sqlite():
    migration = _load_migration_module()
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE staff_users (
                    id INTEGER PRIMARY KEY,
                    display_name VARCHAR(160) NOT NULL,
                    status VARCHAR(24) NOT NULL,
                    primary_role VARCHAR(40) NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO staff_users (id, display_name, status, primary_role)
                VALUES (7, 'Owner', 'active', 'owner')
                """
            )
        )
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        inspector = inspect(connection)

        assert {"tenant", "tenant_membership", "storefront", "storefront_domain"}.issubset(
            inspector.get_table_names()
        )
        tenant = connection.execute(
            text("SELECT slug, kind, status, is_system FROM tenant")
        ).mappings().one()
        assert dict(tenant) == {
            "slug": "mvn",
            "kind": "operator",
            "status": "active",
            "is_system": 1,
        }
        domains = connection.execute(
            text("SELECT hostname, status, is_primary FROM storefront_domain ORDER BY hostname")
        ).mappings().all()
        assert [dict(item) for item in domains] == [
            {"hostname": "mvn.by", "status": "active", "is_primary": 1},
            {"hostname": "www.mvn.by", "status": "active", "is_primary": 0},
        ]
        membership = connection.execute(
            text("SELECT tenant_id, staff_user_id, role, status FROM tenant_membership")
        ).mappings().one()
        assert membership["tenant_id"] > 0
        assert dict(membership) | {"tenant_id": "present"} == {
            "tenant_id": "present",
            "staff_user_id": 7,
            "role": "owner",
            "status": "active",
        }
        storefront_indexes = {item["name"] for item in inspector.get_indexes("storefront")}
        domain_indexes = {item["name"] for item in inspector.get_indexes("storefront_domain")}
        assert "uq_storefront_default_per_tenant" in storefront_indexes
        assert "uq_storefront_primary_domain" in domain_indexes

        migration.downgrade()
        assert not {"tenant", "tenant_membership", "storefront", "storefront_domain"}.intersection(
            inspect(connection).get_table_names()
        )
