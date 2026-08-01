from unittest.mock import AsyncMock

import pytest

from services.catalog_invalidation_commit_service import (
    CatalogInvalidationCommitService,
)
from services.catalog_revision_service import CatalogRevisionService


@pytest.mark.asyncio
async def test_global_catalog_mutation_stages_invalidation_before_commit(monkeypatch):
    session = AsyncMock()
    stage_invalidation = AsyncMock(return_value={"revision": 7})
    monkeypatch.setattr(
        CatalogRevisionService,
        "stage_invalidation",
        stage_invalidation,
    )

    result = await CatalogInvalidationCommitService.commit_global_mutation(
        session,
        reason="brand_update",
        product_ids=[11],
        slugs=["alpha"],
        brand_slugs=["brand-a"],
    )

    stage_invalidation.assert_awaited_once_with(
        session,
        reason="brand_update",
        product_ids=[11],
        slugs=["alpha"],
        brand_slugs=["brand-a"],
    )
    session.commit.assert_awaited_once_with()
    assert result == {"revision": 7}


@pytest.mark.asyncio
async def test_global_catalog_mutation_does_not_commit_when_staging_fails(
    monkeypatch,
):
    session = AsyncMock()
    monkeypatch.setattr(
        CatalogRevisionService,
        "stage_invalidation",
        AsyncMock(side_effect=RuntimeError("outbox unavailable")),
    )

    with pytest.raises(RuntimeError, match="outbox unavailable"):
        await CatalogInvalidationCommitService.commit_global_mutation(
            session,
            reason="brand_update",
        )

    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_registered_catalog_mutation_uses_producer_reason(monkeypatch):
    session = AsyncMock()
    stage_invalidation = AsyncMock(return_value={"revision": 11})
    monkeypatch.setattr(
        CatalogRevisionService,
        "stage_invalidation",
        stage_invalidation,
    )

    result = await CatalogInvalidationCommitService.commit_registered_global_mutation(
        session,
        producer="manager_media.set_main_image",
        changed=True,
        product_ids=[17],
    )

    stage_invalidation.assert_awaited_once_with(
        session,
        reason="product_media_set_main",
        product_ids=[17],
        slugs=None,
        brand_slugs=None,
    )
    session.commit.assert_awaited_once_with()
    assert result == {"revision": 11}


@pytest.mark.asyncio
async def test_registered_catalog_noop_commits_without_revision_or_outbox_stage(
    monkeypatch,
):
    session = AsyncMock()
    stage_invalidation = AsyncMock()
    monkeypatch.setattr(
        CatalogRevisionService,
        "stage_invalidation",
        stage_invalidation,
    )

    result = await CatalogInvalidationCommitService.commit_registered_global_mutation(
        session,
        producer="manager_media.set_main_image",
        changed=False,
        product_ids=[17],
    )

    assert result is None
    stage_invalidation.assert_not_awaited()
    session.commit.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_registered_catalog_mutation_rejects_unknown_producer_before_commit():
    session = AsyncMock()

    with pytest.raises(ValueError, match="Unregistered global catalog mutation producer"):
        await CatalogInvalidationCommitService.commit_registered_global_mutation(
            session,
            producer="manager_media.untracked_write",
            changed=True,
        )

    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_registered_catalog_mutation_does_not_commit_when_staging_fails(
    monkeypatch,
):
    session = AsyncMock()
    monkeypatch.setattr(
        CatalogRevisionService,
        "stage_invalidation",
        AsyncMock(side_effect=RuntimeError("outbox unavailable")),
    )

    with pytest.raises(RuntimeError, match="outbox unavailable"):
        await CatalogInvalidationCommitService.commit_registered_global_mutation(
            session,
            producer="importer.import_product",
            changed=True,
            product_ids=[42],
        )

    session.commit.assert_not_awaited()
