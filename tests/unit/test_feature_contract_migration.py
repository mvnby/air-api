from alembic.config import Config
from alembic.script import ScriptDirectory

from models import Feature, FeatureSeriesLink
from tests.unit.alembic_chain_test_support import (
    assert_revision_in_single_head_chain,
)


def test_feature_contract_migration_is_additive_single_head():
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = script.get_revision("f3a4b5c6d7e8")

    assert_revision_in_single_head_chain(script, revision.revision)
    assert revision.down_revision == "f2a3b4c5d6e7"
    assert Feature.__table__.c.replaces_feature_id.foreign_keys
    assert FeatureSeriesLink.__table__.c.is_featured.nullable is False
    assert any(
        index.name == "ix_feature_series_link_series_featured_sort"
        for index in FeatureSeriesLink.__table__.indexes
    )
