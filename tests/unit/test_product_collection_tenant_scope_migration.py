from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.unit.alembic_chain_test_support import (
    assert_revision_in_single_head_chain,
)


REVISION = "b7c8d9e0f1a2"


def test_product_collection_scope_is_single_head_and_fails_closed() -> None:
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert assert_revision_in_single_head_chain(scripts, REVISION) == REVISION
    source = Path(
        "alembic/versions/b7c8d9e0f1a2_scope_product_collections.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision: str | None = "a6b7c8d9e0f1"' in source
    assert "exactly one system tenant/default storefront" in source
    assert "Refusing to downgrade scoped ProductCollections" in source
    assert "fk_product_collection_fallback_scope" in source
    assert 'initially="DEFERRED"' in source
    assert "fk_product_collection_fallback_delete" in source
    assert 'ondelete="SET NULL"' in source
    assert "fk_product_collection_item_collection_scope" in source
    assert "fk_product_collection_placement_collection_scope" in source
    assert "trg_product_collection_fill_scope" in source
    assert "product_collection_child_fill_scope" in source
