from types import SimpleNamespace

import pytest
from sqlmodel import select

from crud.product import ProductDAO
from models import Product
from services.product_read_service import ProductReadService


def _session(dialect_name: str):
    return SimpleNamespace(bind=SimpleNamespace(dialect=SimpleNamespace(name=dialect_name)))


def _compiled_sql(stmt, dialect_name: str = "postgresql") -> str:
    if dialect_name == "sqlite":
        from sqlalchemy.dialects import sqlite

        dialect = sqlite.dialect()
    else:
        from sqlalchemy.dialects import postgresql

        dialect = postgresql.dialect()
    return str(stmt.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))


def test_common_filters_prefer_typed_heat_with_legacy_fallback_postgres():
    stmt = ProductDAO._apply_common_filters(
        _session("postgresql"),
        select(Product),
        heating_min=-20,
    )

    sql = _compiled_sql(stmt)

    assert "jsonb_extract_path_text" in sql
    assert "'__typed_specs', 'temp_range_heat', 'min'" in sql
    assert "'__filter_min_heat'" in sql
    assert "coalesce" in sql.lower()


def test_common_filters_prefer_typed_wifi_state_with_legacy_fallback_postgres():
    stmt = ProductDAO._apply_common_filters(
        _session("postgresql"),
        select(Product),
        has_wifi=True,
    )

    sql = _compiled_sql(stmt)

    assert "'__typed_specs', 'wifi_state', 'value'" in sql
    assert "'__filter_wifi'" in sql
    assert "IN ('builtin', 'ready')" in sql


def test_common_filters_prefer_typed_indoor_type_with_legacy_fallback_sqlite():
    stmt = ProductDAO._apply_common_filters(
        _session("sqlite"),
        select(Product),
        indoor_types=["duct"],
    )

    sql = _compiled_sql(stmt, "sqlite")

    assert "json_extract(product.specs, '$.__typed_specs.indoor_type.value')" in sql
    assert "json_extract(product.specs, '$.__filter_indoor_type')" in sql
    assert "coalesce" in sql.lower()


@pytest.mark.asyncio
async def test_count_filtered_applies_the_same_smart_search_as_items():
    captured = {}

    class CaptureSession:
        bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        async def execute(self, stmt):
            captured["stmt"] = stmt
            return SimpleNamespace(scalar_one=lambda: 2)

    total = await ProductDAO.count_filtered(
        CaptureSession(),
        search_query="COUNTMARKER",
    )

    sql = _compiled_sql(captured["stmt"])
    assert total == 2
    assert "product.title ILIKE '%%COUNTMARKER%%'" in sql
    assert "tag.title ILIKE '%%COUNTMARKER%%'" in sql


def test_public_catalog_pagination_cap_is_100():
    ProductReadService.validate_public_pagination(page=1, limit=100)

    with pytest.raises(ValueError, match="between 1 and 100"):
        ProductReadService.validate_public_pagination(page=1, limit=101)
