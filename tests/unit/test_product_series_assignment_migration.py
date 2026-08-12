from alembic.config import Config
from alembic.script import ScriptDirectory

from models import Product


REVISION = "f5c6d7e8a9b0"
DOWN_REVISION = "f4b5c6d7e8f9"


def test_product_series_assignment_provenance_is_additive_single_head():
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = script.get_revision(REVISION)

    assert script.get_heads() == [REVISION]
    assert revision.down_revision == DOWN_REVISION
    column = Product.__table__.c.series_assignment_source
    assert column.nullable is False
    assert column.type.length == 16
    assert any(
        constraint.name == "ck_product_series_assignment_source"
        for constraint in Product.__table__.constraints
    )
