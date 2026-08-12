from alembic.config import Config
from alembic.script import ScriptDirectory

from models import Brand, ProductSeries


REVISION = "f4b5c6d7e8f9"
DOWN_REVISION = "f3a4b5c6d7e8"


def test_brand_featured_series_contract_is_additive_single_head():
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = script.get_revision(REVISION)

    assert script.get_heads() == ["f5c6d7e8a9b0"]
    assert revision.down_revision == DOWN_REVISION
    assert Brand.__table__.c.short_description.nullable is True
    assert ProductSeries.__table__.c.is_featured.nullable is False
    assert any(
        index.name == "ix_product_series_brand_featured_public_sort"
        for index in ProductSeries.__table__.indexes
    )
