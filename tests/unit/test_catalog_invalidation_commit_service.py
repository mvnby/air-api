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
