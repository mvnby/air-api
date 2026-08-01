from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import ServiceAttachment, StorageReconciliationCursor
from services.private_attachment_orphan_reconciler import (
    PrivateAttachmentOrphanReconciler,
)
from services.private_attachment_storage_service import (
    PrivateStorageCandidate,
    PrivateStoragePage,
)


@dataclass
class FakeInventoryStorage:
    provider_name: str = "local"
    inventory_id: str = "fake-private-inventory"
    keys: set[str] = field(default_factory=set)
    deleted: list[str] = field(default_factory=list)
    page_calls: list[tuple[str | None, int]] = field(default_factory=list)
    fail_delete_once: bool = False

    async def list_reconciliation_page(
        self,
        *,
        variant_prefixes,
        older_than,
        cursor,
        limit,
    ):
        del variant_prefixes
        self.page_calls.append((cursor, limit))
        remaining = [key for key in sorted(self.keys) if not cursor or key > cursor]
        examined_keys = remaining[:limit]
        wrapped = len(remaining) <= limit
        old = older_than - timedelta(seconds=1)
        return PrivateStoragePage(
            candidates=tuple(
                PrivateStorageCandidate(storage_key=key, modified_at=old)
                for key in examined_keys
            ),
            next_cursor=None if wrapped else examined_keys[-1],
            examined=len(examined_keys),
            wrapped=wrapped,
        )

    async def delete(self, storage_key):
        if self.fail_delete_once:
            self.fail_delete_once = False
            raise OSError("storage unavailable")
        self.deleted.append(storage_key)
        self.keys.discard(storage_key)


@pytest.fixture
async def orphan_factory(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'orphans.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


def _key(index: int, *, family: str = "installation") -> str:
    return f"{index:02d}/hash/public-{family}-{index:02d}-original.png"


@pytest.mark.asyncio
async def test_reconciler_pages_past_referenced_objects_and_resumes_after_restart(
    orphan_factory,
):
    referenced = {_key(0), _key(1), _key(2)}
    orphan = _key(3, family="repair")
    storage = FakeInventoryStorage(keys={*referenced, orphan})
    async with orphan_factory() as setup:
        setup.add_all(
            [
                ServiceAttachment(
                    original_filename=f"photo-{index}.png",
                    mime_type="image/png",
                    content_hash=f"{index:064x}",
                    storage_provider=storage.provider_name,
                    storage_key=key,
                )
                for index, key in enumerate(sorted(referenced), start=1)
            ]
        )
        await setup.commit()

    async with orphan_factory() as first_process:
        first_deleted = await PrivateAttachmentOrphanReconciler.process_batch(
            first_process,
            storage=storage,
            now=datetime.now(timezone.utc),
            limit=2,
            worker_id="first-process",
        )
    async with orphan_factory() as restarted_process:
        second_deleted = await PrivateAttachmentOrphanReconciler.process_batch(
            restarted_process,
            storage=storage,
            now=datetime.now(timezone.utc),
            limit=2,
            worker_id="restarted-process",
        )
        cursor = await restarted_process.scalar(
            select(StorageReconciliationCursor)
        )

    assert first_deleted == 0
    assert second_deleted == 1
    assert storage.deleted == [orphan]
    assert referenced.issubset(storage.keys)
    assert storage.page_calls[0] == (None, 2)
    assert storage.page_calls[1][0] == _key(1)
    assert cursor is not None
    assert cursor.cursor is None
    assert cursor.lease_token is None


@pytest.mark.asyncio
async def test_reconciler_retries_same_page_after_delete_failure(orphan_factory):
    orphan = _key(0, family="repair")
    storage = FakeInventoryStorage(
        keys={orphan},
        fail_delete_once=True,
    )
    async with orphan_factory() as failed_process:
        with pytest.raises(OSError, match="storage unavailable"):
            await PrivateAttachmentOrphanReconciler.process_batch(
                failed_process,
                storage=storage,
                limit=1,
                worker_id="failed-process",
            )
    async with orphan_factory() as restarted_process:
        deleted = await PrivateAttachmentOrphanReconciler.process_batch(
            restarted_process,
            storage=storage,
            limit=1,
            worker_id="restarted-process",
        )

    assert deleted == 1
    assert storage.deleted == [orphan]
    assert storage.page_calls == [(None, 1), (None, 1)]


@pytest.mark.asyncio
async def test_reconciler_lease_uses_database_clock_not_cutoff_clock(orphan_factory):
    storage = FakeInventoryStorage(keys={_key(0)})
    async with orphan_factory() as holder:
        async with holder.begin():
            claim = await PrivateAttachmentOrphanReconciler._claim(
                holder,
                storage=storage,
                worker_id="lease-holder",
            )
        assert claim is not None

    async with orphan_factory() as contender:
        deleted = await PrivateAttachmentOrphanReconciler.process_batch(
            contender,
            storage=storage,
            # This only controls the orphan-age cutoff. It must not expire the
            # durable lease when an application host clock is skewed.
            now=datetime.now(timezone.utc) + timedelta(days=365),
            limit=1,
            worker_id="skewed-contender",
        )

    assert deleted == 0
    assert storage.page_calls == []
