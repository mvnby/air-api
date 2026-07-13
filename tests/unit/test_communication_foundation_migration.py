import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect


REVISION = "3f7a9c1d2e04"
MIGRATION_PATH = Path("alembic/versions/3f7a9c1d2e04_add_communications_outbox_foundation.py")


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("communication_foundation_migration", MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_communication_foundation_is_in_the_single_alembic_head_chain():
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = script.get_revision(REVISION)
    heads = script.get_heads()

    assert len(heads) == 1
    assert revision is not None
    assert revision.down_revision == "2d4f6a8b0c13"
    assert REVISION in {
        item.revision for item in script.iterate_revisions(heads[0], "base")
    }


def test_communication_foundation_migration_upgrades_and_downgrades_sqlite():
    migration = _load_migration_module()
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        inspector = inspect(connection)

        assert {
            "integration_outbox_event",
            "consumer_inbox",
            "communication_delivery",
        }.issubset(inspector.get_table_names())
        assert any(
            item["name"] == "uq_integration_outbox_event_deduplication_key"
            for item in inspector.get_unique_constraints("integration_outbox_event")
        )
        assert any(
            item["name"]
            == "uq_communication_delivery_event_channel_recipient_template"
            and item["column_names"]
            == ["event_id", "channel", "recipient_key", "template_version"]
            for item in inspector.get_unique_constraints("communication_delivery")
        )
        assert any(
            item["name"] == "ck_outbox_status_valid"
            for item in inspector.get_check_constraints("integration_outbox_event")
        )
        assert any(
            item["name"] == "ck_delivery_status_valid"
            for item in inspector.get_check_constraints("communication_delivery")
        )

        migration.downgrade()
        assert not {
            "integration_outbox_event",
            "consumer_inbox",
            "communication_delivery",
        }.intersection(inspect(connection).get_table_names())
