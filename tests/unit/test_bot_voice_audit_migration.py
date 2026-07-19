import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect


REVISION = "9b4d6f8a1c30"
MIGRATION_PATH = Path(
    "alembic/versions/9b4d6f8a1c30_add_bot_voice_transcription_audit.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("bot_voice_audit_migration", MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bot_voice_audit_is_in_single_alembic_head_chain():
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = script.get_revision(REVISION)

    heads = script.get_heads()

    assert len(heads) == 1
    assert revision is not None
    assert revision.down_revision == "8a3c5e7f9b21"
    assert REVISION in {
        item.revision for item in script.iterate_revisions(heads[0], "base")
    }


def test_bot_voice_audit_migration_upgrades_and_downgrades_sqlite():
    migration = _load_migration_module()
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        inspector = inspect(connection)

        assert "bot_voice_transcription_audit" in inspector.get_table_names()
        assert any(
            item["name"] == "ck_bot_voice_audit_status"
            for item in inspector.get_check_constraints(
                "bot_voice_transcription_audit"
            )
        )
        migration.downgrade()
        assert "bot_voice_transcription_audit" not in inspect(
            connection
        ).get_table_names()
