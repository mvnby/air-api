from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from services.catalog_invalidation_commit_service import (
    CatalogInvalidationCommitService,
)
from services.manager_media_service import ManagerMediaService


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _ScalarsResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return list(self._values)


@pytest.mark.asyncio
async def test_set_main_image_full_noop_uses_changed_false(monkeypatch):
    image = SimpleNamespace(id=5, product_id=9, url="/media/products/same.webp")
    product = SimpleNamespace(id=9, main_image=image.url)
    session = AsyncMock()
    session.get.side_effect = [image, product]
    commit_mutation = AsyncMock()
    monkeypatch.setattr(
        CatalogInvalidationCommitService,
        "commit_registered_global_mutation",
        commit_mutation,
    )

    result = await ManagerMediaService.set_main_image(session, image.id)

    assert result["url"] == image.url
    session.add.assert_not_called()
    commit_mutation.assert_awaited_once_with(
        session,
        producer="manager_media.set_main_image",
        changed=False,
        product_ids=[product.id],
    )


@pytest.mark.asyncio
async def test_reusing_fully_linked_image_is_a_catalog_noop(monkeypatch):
    product = SimpleNamespace(id=9)
    image = SimpleNamespace(id=5, product_id=9, url="/media/products/same.webp")
    original_variant = SimpleNamespace(url=image.url, processing_status="ready")
    session = AsyncMock()
    session.get.return_value = product
    session.execute.side_effect = [
        _ScalarResult(image),
        _ScalarResult(original_variant),
    ]
    commit_mutation = AsyncMock()
    monkeypatch.setattr(
        CatalogInvalidationCommitService,
        "commit_registered_global_mutation",
        commit_mutation,
    )

    result = await ManagerMediaService.reuse_image_link(
        session,
        product_id=product.id,
        source_image_url=image.url,
    )

    assert result == {"message": "Image already linked", "id": image.id}
    commit_mutation.assert_awaited_once_with(
        session,
        producer="manager_media.reuse_image_link",
        changed=False,
        product_ids=[product.id],
    )


@pytest.mark.asyncio
async def test_bulk_upload_stages_all_images_before_one_catalog_commit(monkeypatch):
    session = AsyncMock()
    session.execute.return_value = _ScalarsResult([11, 12])
    stage_image = AsyncMock(
        side_effect=[
            ({"id": 1, "url": "/one.webp"}, True),
            ({"id": 2, "url": "/two.webp"}, True),
            ({"id": 3, "url": "/one.webp"}, True),
            ({"id": 4, "url": "/two.webp"}, True),
        ]
    )
    commit_mutation = AsyncMock()
    monkeypatch.setattr(ManagerMediaService, "_stage_image_from_bytes", stage_image)
    monkeypatch.setattr(
        CatalogInvalidationCommitService,
        "commit_registered_global_mutation",
        commit_mutation,
    )

    result = await ManagerMediaService.bulk_upload_local_images(
        session,
        product_ids=[11, 12],
        file_payloads=[b"one", b"two"],
        is_installation=False,
        set_main=True,
    )

    assert result["uploaded_links"] == 4
    assert stage_image.await_count == 4
    commit_mutation.assert_awaited_once_with(
        session,
        producer="manager_media.bulk_upload_local_images",
        changed=True,
        product_ids=[11, 12],
    )
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_media_mutation_does_not_cross_commit_boundary_when_staging_fails(
    monkeypatch,
):
    image = SimpleNamespace(id=5, product_id=9, url="/media/products/new.webp")
    product = SimpleNamespace(id=9, main_image="/media/products/old.webp")
    session = AsyncMock()
    session.add = Mock()
    session.get.side_effect = [image, product]
    monkeypatch.setattr(
        CatalogInvalidationCommitService,
        "commit_registered_global_mutation",
        AsyncMock(side_effect=RuntimeError("outbox unavailable")),
    )

    with pytest.raises(RuntimeError, match="outbox unavailable"):
        await ManagerMediaService.set_main_image(session, image.id)

    assert product.main_image == image.url
    session.commit.assert_not_awaited()
