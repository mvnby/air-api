from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql
from sqlmodel import select

from crud.canonical_public_catalog import CanonicalPublicCatalogDAO
from crud.public_taxonomy import PublicTaxonomyDAO
from models import Product
from services.product_series_service import ProductSeriesService


def _postgres_sql(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


class _EmptyRows:
    def all(self):
        return []


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)

    def scalars(self):
        return self


class _EmptyPublicTaxonomySession:
    bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    def __init__(self) -> None:
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _EmptyRows()


class _QueuedSession(_EmptyPublicTaxonomySession):
    def __init__(self, rows):
        super().__init__()
        self._rows = iter(rows)

    async def execute(self, statement):
        self.statements.append(statement)
        return _Rows(next(self._rows))


@pytest.mark.asyncio
async def test_hidden_and_unknown_filter_slugs_have_identical_neutral_behavior():
    hidden_session = _EmptyPublicTaxonomySession()
    unknown_session = _EmptyPublicTaxonomySession()

    hidden = await PublicTaxonomyDAO.resolve_filter_ids(
        hidden_session,
        tag_slugs=["internal-only"],
        brand_slugs=None,
    )
    unknown = await PublicTaxonomyDAO.resolve_filter_ids(
        unknown_session,
        tag_slugs=["does-not-exist"],
        brand_slugs=None,
    )

    assert hidden == unknown == (None, [])
    for statement in hidden_session.statements + unknown_session.statements:
        sql = _postgres_sql(statement)
        assert "tag.is_public IS true" in sql
        assert "tag_group.is_public IS true" in sql


@pytest.mark.asyncio
async def test_legacy_brand_slug_requires_public_tag_and_published_brand():
    session = _QueuedSession(
        [
            [(7, 3, "brand-a", "brand")],
            ["brand-a"],
        ]
    )

    faceted_ids, brand_slugs = await PublicTaxonomyDAO.resolve_filter_ids(
        session,
        tag_slugs=["brand-a"],
        brand_slugs=None,
    )

    assert faceted_ids is None
    assert brand_slugs == ["brand-a"]
    tag_sql, brand_sql = map(_postgres_sql, session.statements)
    assert "tag.is_public IS true" in tag_sql
    assert "tag_group.is_public IS true" in tag_sql
    assert "brand.is_published IS true" in brand_sql


@pytest.mark.asyncio
async def test_unpublished_legacy_brand_is_neutral_like_unknown_slug():
    hidden_brand_session = _QueuedSession(
        [
            [(7, 3, "hidden-brand", "brand")],
            [],
        ]
    )
    unknown_session = _EmptyPublicTaxonomySession()

    hidden_brand = await PublicTaxonomyDAO.resolve_filter_ids(
        hidden_brand_session,
        tag_slugs=["hidden-brand"],
        brand_slugs=None,
    )
    unknown = await PublicTaxonomyDAO.resolve_filter_ids(
        unknown_session,
        tag_slugs=["does-not-exist"],
        brand_slugs=None,
    )

    assert hidden_brand == unknown == (None, [])


def test_public_q_cannot_match_hidden_tag_title_or_hidden_group():
    session = _EmptyPublicTaxonomySession()
    statement = PublicTaxonomyDAO.apply_search_filter(
        session,
        select(Product),
        "InternalTaxonomyTitle",
    )

    sql = _postgres_sql(statement)
    assert "product.title ILIKE '%%InternalTaxonomyTitle%%'" in sql
    assert "tag.title ILIKE '%%InternalTaxonomyTitle%%'" in sql
    assert "tag.is_public IS true" in sql
    assert "tag_group.is_public IS true" in sql


@pytest.mark.asyncio
async def test_canonical_public_search_selects_public_taxonomy_mode():
    captured = {}

    class _Result:
        def scalars(self):
            return self

        def all(self):
            return []

    class _Session(_EmptyPublicTaxonomySession):
        async def execute(self, statement):
            captured["statement"] = statement
            return _Result()

    products = await CanonicalPublicCatalogDAO.get_filtered(
        _Session(),
        search_query="InternalTaxonomyTitle",
    )

    assert products == []
    sql = _postgres_sql(captured["statement"])
    assert "product.is_published = true" in sql
    assert "tag.is_public IS true" in sql
    assert "tag_group.is_public IS true" in sql


def test_series_group_keys_ignore_hidden_taxonomy():
    public_group = SimpleNamespace(slug="series", is_public=True)
    hidden_group = SimpleNamespace(slug="series", is_public=False)
    product = SimpleNamespace(
        series_id=None,
        tags=[
            SimpleNamespace(id=1, is_public=True, group=public_group),
            SimpleNamespace(id=2, is_public=False, group=public_group),
            SimpleNamespace(id=3, is_public=True, group=hidden_group),
        ],
        specs={},
    )

    assert ProductSeriesService._series_group_keys(product) == ["tag:1"]
