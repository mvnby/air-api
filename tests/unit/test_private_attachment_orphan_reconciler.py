from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from models import ServiceAttachment
from services.private_attachment_orphan_reconciler import (
    PrivateAttachmentOrphanReconciler,
)
from services.private_attachment_storage_service import PrivateStorageCandidate


@dataclass
class FakeInventoryStorage:
    provider_name: str = "local"
    keys: set[str] = field(default_factory=set)
    deleted: list[str] = field(default_factory=list)

    async def list_variant_candidates(self, **_kwargs):
        old = datetime.now(timezone.utc) - timedelta(days=2)
        return [
            PrivateStorageCandidate(storage_key=key, modified_at=old)
            for key in sorted(self.keys)
        ]

    async def delete(self, storage_key):
        self.deleted.append(storage_key)
        self.keys.discard(storage_key)


@pytest.fixture
async def orphan_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'orphans.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_orphan_reconciler_preserves_referenced_key_after_grace(orphan_session):
    referenced = (
        "aa/bb/hash/"
        "public-installation-referenced-original.png"
    )
    orphan = "cc/dd/hash/public-installation-orphan-original.png"
    storage = FakeInventoryStorage(keys={referenced, orphan})
    orphan_session.add(
        ServiceAttachment(
            original_filename="photo.png",
            mime_type="image/png",
            content_hash="a" * 64,
            storage_provider=storage.provider_name,
            storage_key=referenced,
        )
    )
    await orphan_session.commit()

    deleted = await PrivateAttachmentOrphanReconciler.process_batch(
        orphan_session,
        storage=storage,
        now=datetime.now(timezone.utc),
    )

    assert deleted == 1
    assert storage.deleted == [orphan]
    assert referenced in storage.keys
