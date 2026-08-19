from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql
from sqlmodel import select

from crud.canonical_public_catalog import CanonicalPublicCatalogDAO
from crud.public_catalog import PublicCatalogDAO
from crud.public_taxonomy import PublicTaxonomyDAO
from models import Product
from models.tenancy import TenantScope
from services.feature_resolver_service import FeatureResolverService
from services.public_catalog_service import PublicCatalogService
from services.public_catalog_visibility_service import (
    PublicCatalogVisibilityService,
    PublicProductProjection,
)
from services.public_catalog_disclosure import TENANT_NEUTRAL_PUBLIC_DISCLOSURE
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

    def scalars(self):
        return self


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


def test_hidden_series_id_does_not_override_public_fallback_group_key():
    product = SimpleNamespace(
        series_id=77,
        series=SimpleNamespace(id=77, is_published=False),
        tags=[
            SimpleNamespace(
                id=1,
                is_public=True,
                group=SimpleNamespace(slug="series", is_public=True),
            )
        ],
        specs={"series": "Public fallback"},
    )

    assert ProductSeriesService._series_group_keys(product) == [
        "tag:1",
        "specs:public fallback",
    ]


class _FailIfExecuted:
    async def execute(self, _statement):
        raise AssertionError("hidden series must not issue a sibling query")


@pytest.mark.asyncio
async def test_hidden_series_cannot_drive_canonical_detail_siblings():
    product = SimpleNamespace(
        id=10,
        series_id=77,
        series=SimpleNamespace(id=77, is_published=False),
        tags=[],
        specs={},
    )

    siblings = await ProductSeriesService.get_series_siblings(
        _FailIfExecuted(),
        product,
    )

    assert siblings == []


@pytest.mark.asyncio
async def test_hidden_series_cannot_drive_offer_scoped_detail_siblings():
    product = SimpleNamespace(
        id=10,
        series_id=77,
        series=SimpleNamespace(id=77, is_published=False),
        tags=[],
        specs={},
    )

    siblings = await PublicCatalogDAO.get_series_siblings(
        _FailIfExecuted(),
        tenant_scope=SimpleNamespace(tenant_id=1, storefront_id=2),
        product=product,
    )

    assert siblings == []


def _series_sort_product(
    product_id: int,
    *,
    brand_tag_id: int,
):
    return SimpleNamespace(
        id=product_id,
        title=f"Product {product_id}",
        brand_id=99,
        brand=SimpleNamespace(id=99, is_published=False),
        tags=[
            SimpleNamespace(
                id=brand_tag_id,
                is_public=True,
                group=SimpleNamespace(slug="brand", is_public=True),
            )
        ],
        specs={"area_m2": 25},
        power_cooling=2.5,
        price=1000,
    )


def test_hidden_brand_id_does_not_influence_canonical_sibling_order():
    reference = _series_sort_product(1, brand_tag_id=10)
    hidden_id_match = _series_sort_product(2, brand_tag_id=20)
    public_tag_match = _series_sort_product(3, brand_tag_id=10)

    ordered = ProductSeriesService._sort_series_candidates(
        reference,
        [hidden_id_match, public_tag_match],
    )

    assert [item.id for item in ordered] == [3, 2]


def test_hidden_brand_id_does_not_influence_offer_sibling_order():
    reference = PublicProductProjection(
        product=_series_sort_product(1, brand_tag_id=10),
        price=1000,
        old_price=None,
        disclosure_policy=TENANT_NEUTRAL_PUBLIC_DISCLOSURE,
    )
    hidden_id_match = PublicProductProjection(
        product=_series_sort_product(2, brand_tag_id=20),
        price=1000,
        old_price=None,
        disclosure_policy=TENANT_NEUTRAL_PUBLIC_DISCLOSURE,
    )
    public_tag_match = PublicProductProjection(
        product=_series_sort_product(3, brand_tag_id=10),
        price=1000,
        old_price=None,
        disclosure_policy=TENANT_NEUTRAL_PUBLIC_DISCLOSURE,
    )

    ordered = PublicCatalogService._sort_series_projections(
        reference,
        [hidden_id_match, public_tag_match],
    )

    assert [item.product.id for item in ordered] == [3, 2]


@pytest.mark.asyncio
async def test_hidden_series_is_absent_from_offer_navigation(monkeypatch):
    hidden_series = SimpleNamespace(id=77, is_published=False)
    products = [
        SimpleNamespace(
            id=product_id,
            slug=f"hidden-series-{product_id}",
            series_id=77,
            series=hidden_series,
            tags=[],
            specs={},
        )
        for product_id in (1, 2)
    ]

    async def fake_is_canonical(_session, _scope):
        return False

    async def fake_get_all(_session, *, tenant_scope, load_image_variants=False):
        assert tenant_scope.storefront_id == 2
        assert load_image_variants is False
        return [(product, 1000, None) for product in products]

    async def fake_resolve(_session, candidates):
        assert candidates == products

    monkeypatch.setattr(
        PublicCatalogVisibilityService,
        "is_canonical_scope",
        fake_is_canonical,
    )
    monkeypatch.setattr(PublicCatalogDAO, "get_all", fake_get_all)
    monkeypatch.setattr(
        FeatureResolverService,
        "resolve_for_products",
        fake_resolve,
    )

    navigation = await PublicCatalogService.get_series_navigation(
        object(),
        tenant_scope=TenantScope(
            tenant_id=1,
            storefront_id=2,
            is_canonical_storefront=False,
        ),
    )

    assert navigation.products == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sort", "expected_order"),
    [
        ("price_asc", "product.price ASC, product.id ASC"),
        ("price_desc", "product.price DESC, product.id DESC"),
        ("area_asc", " ASC, product.id ASC"),
        ("area_desc", " DESC, product.id DESC"),
    ],
)
async def test_canonical_price_and_area_sorts_have_stable_id_tie_breaker(
    sort,
    expected_order,
):
    session = _EmptyPublicTaxonomySession()

    await CanonicalPublicCatalogDAO.get_filtered(session, sort=sort)

    sql = _postgres_sql(session.statements[0])
    order_by = sql.split(" ORDER BY ", maxsplit=1)[1]
    assert expected_order in order_by
