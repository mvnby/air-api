from unittest.mock import AsyncMock, MagicMock

import pytest

from models import Brand, ProductSeries
from services.catalog_invalidation_commit_service import CatalogInvalidationCommitService
from services.manager_brand_service import ManagerBrandService


@pytest.mark.asyncio
async def test_series_response_keeps_own_save_when_another_writer_commits(monkeypatch):
    brand = Brand(id=2, title="Brand", slug="brand")
    series = ProductSeries(id=7, brand_id=2, title="Before", slug="series")
    stored_features = [{"id": 101, "is_featured": True}]
    session = MagicMock()
    session.get = AsyncMock(return_value=brand)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    count_result = MagicMock()
    count_result.scalar_one.return_value = 4
    session.execute = AsyncMock(return_value=count_result)
    monkeypatch.setattr(ManagerBrandService, "_get_brand_series", AsyncMock(return_value=series))
    monkeypatch.setattr(ManagerBrandService, "_sync_series_feature_assignments", AsyncMock(return_value=True))

    async def load_features(*args):
        return {7: [dict(item) for item in stored_features]}

    async def commit_then_competing_save(*args, **kwargs):
        series.title = "Next writer"
        stored_features[:] = [{"id": 202, "is_featured": False}]

    monkeypatch.setattr(ManagerBrandService, "_load_series_brand_features", load_features)
    commit = AsyncMock(side_effect=commit_then_competing_save)
    monkeypatch.setattr(CatalogInvalidationCommitService, "commit_registered_global_mutation", commit)

    response = await ManagerBrandService.update_brand_series(
        session,
        2,
        7,
        {"title": "My save", "feature_assignments": [{"feature_id": 101, "is_featured": True}]},
    )

    assert response["title"] == "My save"
    assert response["feature_assignments"] == [{"feature_id": 101, "is_featured": True}]
    assert response["brand_features"] == [{"id": 101, "is_featured": True}]
    assert response["products_count"] == 4
    commit.assert_awaited_once_with(
        session,
        producer="manager_brand.update_brand_series",
        changed=True,
        brand_slugs=["brand"],
    )
