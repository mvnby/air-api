from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from models import Brand, FeatureSeriesLink, ProductSeries, Tag, TagGroup
from services.manager_brand_series_service import ManagerBrandSeriesOperations
from services.manager_brand_service import ManagerBrandService


@pytest.mark.asyncio
async def test_sync_brand_tag_returns_noop_before_any_tag_write(monkeypatch):
    group = TagGroup(id=1, title="Бренд", slug="brand")
    brand = Brand(id=2, title="Exact Brand", slug="exact-brand")
    tag = Tag(
        id=3,
        group_id=group.id,
        title=brand.title,
        slug=brand.slug,
        is_public=True,
        is_filter=True,
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = tag
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.flush = AsyncMock()
    session.add = Mock()
    monkeypatch.setattr(
        ManagerBrandService,
        "_ensure_brand_group",
        AsyncMock(return_value=(group, False)),
    )

    changed = await ManagerBrandService._sync_brand_tag(
        session,
        brand=brand,
        previous_slug=brand.slug,
    )

    assert changed is False
    session.add.assert_not_called()
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_series_features_treats_reordered_same_ids_as_noop():
    series = ProductSeries(
        id=7,
        brand_id=2,
        title="Exact Series",
        slug="exact-series",
    )
    links = [
        FeatureSeriesLink(id=11, series_id=7, feature_id=101, sort_order=10),
        FeatureSeriesLink(id=12, series_id=7, feature_id=202, sort_order=20),
    ]
    result = MagicMock()
    result.scalars.return_value.all.return_value = links
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.delete = AsyncMock()
    session.add = Mock()

    changed = await ManagerBrandSeriesOperations._sync_series_brand_features(
        session,
        series=series,
        brand_id=2,
        feature_ids=[202, 101, 202],
    )

    assert changed is False
    session.execute.assert_awaited_once()
    session.delete.assert_not_awaited()
    session.add.assert_not_called()
