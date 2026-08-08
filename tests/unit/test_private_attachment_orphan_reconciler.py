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
    older_than_calls: list[datetime] = field(default_factory=list)
    modified_at_by_key: dict[str, datetime] = field(default_factory=dict)
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
        self.older_than_calls.append(older_than)
        remaining = [
            key
            for key in sorted(self.keys)
            if (not cursor or key > cursor)
            and self.modified_at_by_key.get(
                key,
                older_than - timedelta(seconds=1),
            )
            <= older_than
        ]
        examined_keys = remaining[:limit]
        wrapped = len(remaining) <= limit
        return PrivateStoragePage(
            candidates=tuple(
                PrivateStorageCandidate(
                    storage_key=key,
                    modified_at=self.modified_at_by_key.get(
                        key,
                        older_than - timedelta(seconds=1),
                    ),
                )
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
            # Compatibility caller clocks must affect neither the durable
            # lease nor orphan-age eligibility.
            now=datetime.now(timezone.utc) + timedelta(days=365),
            limit=1,
            worker_id="skewed-contender",
        )

    assert deleted == 0
    assert storage.page_calls == []


@pytest.mark.asyncio
async def test_reconciler_cutoff_uses_claim_database_clock_and_keeps_fresh_upload(
    orphan_factory,
    monkeypatch,
):
    database_now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    stale = _key(0, family="repair")
    fresh_in_flight = _key(1, family="repair")
    storage = FakeInventoryStorage(
        keys={stale, fresh_in_flight},
        modified_at_by_key={
            stale: database_now - timedelta(hours=25),
            fresh_in_flight: database_now - timedelta(minutes=1),
        },
    )

    async def fixed_database_now(_session):
        return database_now

    monkeypatch.setattr(
        PrivateAttachmentOrphanReconciler,
        "_database_now",
        fixed_database_now,
    )
    async with orphan_factory() as session:
        deleted = await PrivateAttachmentOrphanReconciler.process_batch(
            session,
            storage=storage,
            now=database_now + timedelta(days=365),
            limit=10,
            worker_id="skewed-app-clock",
        )

    assert deleted == 1
    assert storage.deleted == [stale]
    assert fresh_in_flight in storage.keys
    assert storage.older_than_calls == [database_now - timedelta(hours=24)]
