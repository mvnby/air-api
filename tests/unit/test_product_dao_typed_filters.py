from types import SimpleNamespace

from sqlmodel import select

from crud.product import ProductDAO
from models import Product


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
