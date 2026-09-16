from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from api_contracts.product_collections import ProductCollectionPlacementDisplayConfig
from models.tenancy import TenantScope
from services.product_collection_placement_display import display_config, present_items, select_daily_collections, present_collections
from services.product_collection_resolver import ProductCollectionResolver


@pytest.mark.parametrize("config", [
    {"display_mode": "other"}, {"item_limit": 0}, {"item_limit": 25},
    {"grid_columns": 1}, {"grid_columns": 5}, {"rotation_mode": "weekly"},
    {"display_mode": "grid", "rotation_mode": "daily"},
])
def test_display_config_rejects_invalid_options(config):
    with pytest.raises(ValidationError):
        ProductCollectionPlacementDisplayConfig(**config)


def test_daily_presentation_is_stable_and_preserves_ordinary_rows():
    rows = [
        {"slug": "ordinary", **display_config()},
        {"slug": "a", **display_config(), "display_mode": "single", "rotation_mode": "daily"},
        {"slug": "b", **display_config(), "display_mode": "single", "rotation_mode": "daily"},
    ]
    assert [row["slug"] for row in select_daily_collections(rows, day=10)] == ["ordinary", "a"]
    assert [row["slug"] for row in select_daily_collections(rows, day=11)] == ["ordinary", "b"]
    items = [{"product": {"id": index}, "position": index} for index in range(4)]
    config = {**rows[1], "item_limit": 2}
    assert present_items(items, config, day=11) == [{"product": {"id": 1}, "position": 0}]
    assert present_items(items, {**config, "rotation_mode": "none"}, day=11)[0]["product"]["id"] == 0


@pytest.mark.asyncio
async def test_placement_presentation_applies_after_minimum_and_skips_ineligible_daily(monkeypatch):
    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True)
    now = datetime(2026, 9, 16, tzinfo=timezone.utc)
    from services import product_collection_resolver as module
    monkeypatch.setattr(module, "utc_now", lambda: now)
    monkeypatch.setattr(module.PublicCatalogVisibilityService, "is_canonical_scope", AsyncMock(return_value=True))
    rows = []
    for index, mode, rotation in [(0, "grid", "none"), (1, "single", "daily"), (2, "single", "daily")]:
        placement = SimpleNamespace(position=index, **{**display_config(), "display_mode": mode, "rotation_mode": rotation, "item_limit": 1})
        collection = SimpleNamespace(id=index, slug=str(index), public_title=str(index), public_description=None, public_badge=None, cta_label=None, cta_url=None, updated_at=now, min_items=3)
        rows.append((placement, collection))
    monkeypatch.setattr(module.ProductCollectionDAO, "list_placements", AsyncMock(return_value=rows))
    async def resolve(*args, collection, **kwargs):
        return {"below_min_items": collection.id == 1, "items": [{"product": {"id": i}, "position": i} for i in range(3)]}
    monkeypatch.setattr(ProductCollectionResolver, "resolve", resolve)
    response = await ProductCollectionResolver.resolve_placement(AsyncMock(), surface_key="home", slot_key="after_featured", tenant_scope=scope)
    assert [row["slug"] for row in response["collections"]] == ["0", "2"]
    assert all(len(row["items"]) == 1 for row in response["collections"])


def test_daily_rotation_visits_every_product_in_every_collection():
    def row(slug, mode="single", rotation="daily"):
        return {
            "slug": slug, **display_config(), "display_mode": mode,
            "rotation_mode": rotation, "item_limit": 2,
            "items": [{"product": {"id": f"{slug}-{i}"}, "position": i} for i in range(3)],
        }
    rows = [row("ordinary", "grid", "none"), row("a"), row("b")]
    seen = {"a": set(), "b": set()}
    for day in range(8):
        displayed = present_collections(rows, day=day)
        assert [item["product"]["id"] for item in displayed[0]["items"]] == ["ordinary-0", "ordinary-1"]
        chosen = displayed[1]
        assert len(chosen["items"]) == 1
        assert chosen["slug"] == ("a" if day % 2 == 0 else "b")
        seen[chosen["slug"]].add(chosen["items"][0]["product"]["id"])
    assert seen == {"a": {"a-0", "a-1"}, "b": {"b-0", "b-1"}}
