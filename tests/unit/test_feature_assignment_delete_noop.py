from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import pytest

from services.catalog_invalidation_commit_service import (
    CatalogInvalidationCommitService,
)
from services.feature_assignment_service import FeatureAssignmentService


@pytest.mark.asyncio
async def test_repeated_target_delete_marks_only_the_first_call_as_changed(monkeypatch):
    session = AsyncMock()
    session.execute.side_effect = [
        SimpleNamespace(),
        SimpleNamespace(rowcount=1),
        SimpleNamespace(),
        SimpleNamespace(rowcount=0),
    ]
    commit_mutation = AsyncMock()
    monkeypatch.setattr(
        CatalogInvalidationCommitService,
        "commit_registered_global_mutation",
        commit_mutation,
    )

    for _ in range(2):
        await FeatureAssignmentService.delete_target_link(
            session,
            feature_id=7,
            target_type="brand",
            target_id=13,
        )

    assert commit_mutation.await_args_list == [
        call(
            session,
            producer="feature_assignment.delete_target_link.brand",
            changed=True,
        ),
        call(
            session,
            producer="feature_assignment.delete_target_link.brand",
            changed=False,
        ),
    ]


@pytest.mark.asyncio
async def test_missing_product_assignment_delete_is_a_catalog_noop(monkeypatch):
    session = AsyncMock()
    session.get.return_value = object()
    session.execute.return_value = SimpleNamespace(rowcount=0)
    commit_mutation = AsyncMock()
    workspace = object()
    monkeypatch.setattr(
        CatalogInvalidationCommitService,
        "commit_registered_global_mutation",
        commit_mutation,
    )
    monkeypatch.setattr(
        FeatureAssignmentService,
        "get_product_workspace",
        AsyncMock(return_value=workspace),
    )

    result = await FeatureAssignmentService.delete_product_assignment(
        session,
        product_id=19,
        feature_id=23,
    )

    assert result is workspace
    commit_mutation.assert_awaited_once_with(
        session,
        producer="feature_assignment.delete_product_assignment",
        changed=False,
        product_ids=[19],
    )
