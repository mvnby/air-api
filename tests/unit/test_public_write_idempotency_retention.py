from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, func, select

from models import PublicWriteIdempotency, Storefront, Tenant
from services.public_write_idempotency_retention_service import (
    PublicWriteIdempotencyRetentionService,
)


@pytest.fixture
async def retention_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'retention.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_retention_deletes_only_expired_receipts(retention_session):
    now = datetime.now(timezone.utc)
    retention_session.add(
        Tenant(id=1, slug="retention", display_name="Retention")
    )
    retention_session.add(
        Storefront(
            id=1,
            tenant_id=1,
            slug="main",
            display_name="Main",
            status="active",
            is_default=True,
        )
    )
    for index, expires_at in enumerate(
        (now - timedelta(seconds=1), now + timedelta(days=1)),
        start=1,
    ):
        retention_session.add(
            PublicWriteIdempotency(
                tenant_id=1,
                storefront_id=1,
                command_name="public_contact_lead_v1",
                key_hash=f"{index:064x}",
                request_fingerprint=f"{index + 10:064x}",
                expires_at=expires_at,
            )
        )
    await retention_session.commit()

    deleted = await PublicWriteIdempotencyRetentionService.delete_expired_batch(
        retention_session,
        now=now,
    )
    await retention_session.commit()

    assert deleted == 1
    assert (
        await retention_session.scalar(
            select(func.count(PublicWriteIdempotency.id))
        )
        == 1
    )
