"""Actual PostgreSQL publication, revision/outbox atomicity and no-op boundary."""

from copy import deepcopy
import json
import re

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from crud.catalog_revision import CatalogRevisionDAO
from feature_media_publication_test_support import publication_fixture
from models import (Brand, Feature, FeatureBrandLink, FeatureCategory, FeatureProductLink,
    FeatureRule, FeatureSeriesLink, IntegrationOutboxEvent, MediaAsset, Product, ProductSeries)
from services.feature_media_publication import PublicationBlocked, run
from services.catalog_revision_service import CatalogRevisionService


async def snapshot(factory):
    async with factory() as session:
        result = {}
        for model in (Feature, FeatureRule, FeatureBrandLink, FeatureSeriesLink,
            FeatureProductLink, Product, ProductSeries, MediaAsset, IntegrationOutboxEvent):
            rows = (await session.execute(select(model))).scalars().all()
            result[model.__tablename__] = [row.model_dump() for row in rows]
        result["revision"] = (await CatalogRevisionDAO.get_current(session)).revision
        return deepcopy(result)


@pytest.mark.asyncio
async def test_publication_is_read_only_until_exact_review_and_rolls_back_atomically(
    db_engine, monkeypatch, tmp_path,
):
    assert db_engine.dialect.name == "postgresql"
    assert re.search(r"(?:^|_)test(?:_|$)", db_engine.url.database)
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    import core.database
    monkeypatch.setattr(core.database, "async_session_maker", factory)
    manifest, features, assets = publication_fixture()
    manifest_path = tmp_path / "feature-media-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    async with factory() as session:
        session.add_all([Brand(id=1, title="Reviewed", slug="reviewed"),
            Brand(id=2, title="Other brand", slug="outside-reviewed-brands"),
            FeatureCategory(id=1, slug="fixture", name="Fixture")])
        await session.flush()
        session.add_all([ProductSeries(id=id, brand_id=id, slug=f"series-{id}", title=f"Series {id}")
            for id in (1, 2)])
        session.add_all([MediaAsset(**vars(asset)) for asset in assets])
        session.add_all([Feature(**vars(feature)) for feature in features])
        await session.flush()
        session.add_all([Product(id=id, brand_id=id, series_id=id, slug=f"product-{id}",
            title=f"Product {id}", price=1000, specs={"preserve": True}) for id in (1, 2)])
        await session.flush()
        session.add_all([
            FeatureRule(feature_id=40, spec_key="wifi_ready", operator="eq", target_value=True),
            FeatureBrandLink(brand_id=2, feature_id=7, source="manual"),
            FeatureSeriesLink(series_id=1, feature_id=40, source="manual", display_mode="detailed"),
            FeatureProductLink(product_id=2, feature_id=73, source="derived"),
        ])
        await session.commit()
    baseline = await snapshot(factory)
    reviewed = await run(manifest_path=manifest_path)
    assert reviewed["changed"] == 35 and reviewed["ready"] is True
    assert reviewed["affected_scope"]["product_ids"] == [1, 2]
    assert "outside-reviewed-brands" in reviewed["affected_scope"]["brand_slugs"]
    assert await snapshot(factory) == baseline
    reviewed_path = tmp_path / "reviewed.json"
    reviewed_path.write_text(json.dumps(reviewed), encoding="utf-8")
    with pytest.raises(PublicationBlocked, match="digest"):
        await run(manifest_path=manifest_path, execute=True,
            reviewed_plan=reviewed_path, execute_plan_digest="0" * 64)
    assert await snapshot(factory) == baseline

    real_stage = CatalogRevisionService.stage_invalidation
    staged = []

    async def fail_after_staging(session, **kwargs):
        revision = await real_stage(session, **kwargs)
        assert revision["revision"] == 1
        assert (await session.get(Feature, 40)).icon_media_id == 10040
        assert len((await session.execute(select(IntegrationOutboxEvent))).scalars().all()) == 1
        staged.append(True)
        raise RuntimeError("failure after real revision/outbox staging")

    with monkeypatch.context() as failure:
        failure.setattr(CatalogRevisionService, "stage_invalidation", fail_after_staging)
        with pytest.raises(RuntimeError, match="real revision/outbox"):
            await run(manifest_path=manifest_path, execute=True,
                reviewed_plan=reviewed_path, execute_plan_digest=reviewed["plan_digest"])
    assert staged == [True]
    assert await snapshot(factory) == baseline

    result = await run(manifest_path=manifest_path, execute=True,
        reviewed_plan=reviewed_path, execute_plan_digest=reviewed["plan_digest"])
    assert result["changed"] == 35 and result["revision"]["revision"] == 1
    after = await snapshot(factory)
    assert after["revision"] == 1
    for table in ("feature_rule", "feature_brand_link", "feature_series_link", "feature_product_link",
        "product", "product_series", "media_asset"):
        assert after[table] == baseline[table]
    originals = {row["id"]: row for row in baseline["feature"]}
    for row in after["feature"]:
        for field, value in row.items():
            if field not in {"icon_media_id", "image_media_id", "image_url"}:
                assert value == originals[row["id"]][field]
    events = after["integration_outbox_event"]
    assert len(events) == 1 and events[0]["status"] == "pending"
    payload = events[0]["payload"]
    assert payload["scope"] == "global"
    assert payload["reason"] == "reviewed_feature_media_publication"
    assert {"/product/product-1/", "/product/product-2/",
        "/brands/outside-reviewed-brands/series/series-2/"} <= set(payload["paths"])
    # A completed old review is stale: a fresh no-op plan is required.
    with pytest.raises(PublicationBlocked, match="changed since review"):
        await run(manifest_path=manifest_path, execute=True,
            reviewed_plan=reviewed_path, execute_plan_digest=reviewed["plan_digest"])
    noop = await run(manifest_path=manifest_path)
    assert noop["changed"] == 0
    reviewed_path.write_text(json.dumps(noop), encoding="utf-8")
    result = await run(manifest_path=manifest_path, execute=True,
        reviewed_plan=reviewed_path, execute_plan_digest=noop["plan_digest"])
    assert result["changed"] == 0 and result["revision"] is None
    assert await snapshot(factory) == after
