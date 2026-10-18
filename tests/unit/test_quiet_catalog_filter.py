"""Quiet catalog selection uses normalized facts before paging/counting."""
import json
import sqlite3
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import sqlite
from sqlmodel import select

from crud.product import ProductDAO
from crud.canonical_public_catalog import CanonicalPublicCatalogDAO
from crud.public_catalog import PublicCatalogDAO
from models import Product
from models.tenancy import TenantScope
from services.public_catalog_service import PublicCatalogService
from services.public_catalog_visibility_service import PublicCatalogVisibilityService
from crud.public_taxonomy import PublicTaxonomyDAO


def test_quiet_filter_excludes_unknown_zero_and_loud_models_before_paging():
    session = SimpleNamespace(bind=SimpleNamespace(dialect=sqlite.dialect()))
    statement = ProductDAO._apply_common_filters(
        session, select(Product.id), max_noise_min_db=25,
    ).order_by(Product.id).limit(2)
    sql = str(statement.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE product (id INTEGER, specs JSON, is_published BOOLEAN)")
        values = [None, 0, 26, 25.5, 25, 19, 22]
        db.executemany("INSERT INTO product VALUES (?, ?, 1)", [
            (i, json.dumps({} if noise is None else {"__filter_noise_min": noise}))
            for i, noise in enumerate(values, 1)
        ])
        assert db.execute(sql).fetchall() == [(5,), (6,)]


@pytest.mark.asyncio
@pytest.mark.parametrize("canonical", [True, False])
async def test_quiet_tag_reaches_both_item_and_count_queries(monkeypatch, canonical):
    seen = []
    async def is_canonical(*args): return canonical
    async def resolve(*args, **kwargs): return None, []
    async def items(*args, **kwargs): seen.append(("items", kwargs)); return []
    async def count(*args, **kwargs): seen.append(("count", kwargs)); return 7
    async def discounts(*args): return []
    monkeypatch.setattr(PublicCatalogVisibilityService, "is_canonical_scope", is_canonical)
    monkeypatch.setattr(PublicTaxonomyDAO, "resolve_filter_ids", resolve)
    dao = CanonicalPublicCatalogDAO if canonical else PublicCatalogDAO
    monkeypatch.setattr(dao, "get_filtered", items)
    monkeypatch.setattr(dao, "count_filtered", count)
    monkeypatch.setattr(PublicCatalogService, "_with_installation_discounts", discounts)
    result = await PublicCatalogService.get_catalog_page(
        object(), tenant_scope=TenantScope(tenant_id=1, storefront_id=1),
        tag_slugs=["cat-household", "noise-silent"], page=2, limit=3,
    )
    assert result["meta"] == {"total": 7, "page": 2, "limit": 3, "pages": 3}
    assert {kind for kind, _ in seen} == {"items", "count"}
    assert all(kwargs["max_noise_min_db"] == 25 for _, kwargs in seen)
    assert seen[0][1]["page"] == 2
    assert seen[0][1]["limit"] == 3


def test_derived_quiet_selection_normalizes_legacy_slug():
    from services.public_catalog_filters import quiet_catalog_noise_limit
    assert quiet_catalog_noise_limit([" Noise-Silent "]) == 25
    assert quiet_catalog_noise_limit(["unknown-filter"]) is None
    assert quiet_catalog_noise_limit(None) is None
