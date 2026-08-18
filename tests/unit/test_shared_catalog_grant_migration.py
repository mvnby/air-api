from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.unit.alembic_chain_test_support import (
    assert_revision_in_single_head_chain,
)


REVISION = "a6b7c8d9e0f1"


def test_shared_catalog_grant_is_single_head_and_downgrade_fails_closed() -> None:
    config = Config("alembic.ini")
    scripts = ScriptDirectory.from_config(config)
    assert_revision_in_single_head_chain(scripts, REVISION)
    source = Path(
        "alembic/versions/a6b7c8d9e0f1_add_shared_catalog_grants.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision: str | None = "f5c6d7e8a9b0"' in source
    assert "WHERE catalog_grant_id IS NOT NULL" in source
    assert "status = 'disabled', is_published = false" in source
