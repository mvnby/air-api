import hashlib
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import Order, OrderAttachmentLink, ServiceAttachment
from services.private_attachment_storage_service import StoredPrivateObject
from services.service_attachment_service import ServiceAttachmentService


class FakePrivateAttachmentStorage:
    provider_name = "test_private"

    def __init__(self) -> None:
        self.saved: list[dict] = []

    async def save(self, **kwargs) -> StoredPrivateObject:
        self.saved.append(kwargs)
        return StoredPrivateObject(
            provider=self.provider_name,
            storage_key=f"private/{kwargs['content_hash']}/{kwargs['variant']}.{kwargs['extension']}",
            content_hash=kwargs["content_hash"],
            size_bytes=len(kwargs["content"]),
        )

    async def read(self, storage_key: str) -> bytes:
        raise FileNotFoundError(storage_key)

    async def presign(
        self,
        storage_key: str,
        *,
        expires_seconds: int,
        download_name: str | None = None,
    ) -> str | None:
        return None


@pytest.fixture
async def attachment_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'service-attachments.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)

    factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_private_attachment_hash_dedupe_and_link_level_archive(attachment_session):
    storage = FakePrivateAttachmentStorage()
    first_order = Order(title="First service visit")
    second_order = Order(title="Second service visit")
    attachment_session.add_all([first_order, second_order])
    await attachment_session.commit()

    content = b"private service report"
    first = await ServiceAttachmentService.create_and_link_order_attachment(
        attachment_session,
        order_id=int(first_order.id),
        content=content,
        filename="report.txt",
        mime_type="text/plain",
        category="document",
        storage=storage,
    )
    second = await ServiceAttachmentService.create_and_link_order_attachment(
        attachment_session,
        order_id=int(second_order.id),
        content=content,
        filename="same-content.txt",
        mime_type="text/plain",
        category="service",
        storage=storage,
    )

    attachments = list((await attachment_session.execute(select(ServiceAttachment))).scalars().all())
    links = list((await attachment_session.execute(select(OrderAttachmentLink))).scalars().all())
    assert first["id"] == second["id"]
    assert len(attachments) == 1
    assert len(links) == 2
    assert len(storage.saved) == 1
    assert attachments[0].content_hash == hashlib.sha256(content).hexdigest()
    assert attachments[0].storage_provider == "test_private"
    assert attachments[0].storage_key.startswith("private/")

    access = await ServiceAttachmentService.get_access(
        attachment_session,
        attachment_id=first["id"],
        variant="original",
        download=True,
        storage=storage,
    )
    assert access is not None
    parsed = urlparse(access["url"])
    query = parse_qs(parsed.query)
    assert parsed.path == f"/api/manager/service-attachments/{first['id']}/content"
    assert "private/" not in access["url"]
    assert ServiceAttachmentService.validate_local_signature(
        attachment_id=first["id"],
        variant="original",
        expires=int(query["expires"][0]),
        download=True,
        signature=query["signature"][0],
    )

    assert await ServiceAttachmentService.archive_attachment(
        attachment_session,
        attachment_id=first["id"],
        order_id=int(first_order.id),
    )
    await attachment_session.refresh(attachments[0])
    first_link = next(link for link in links if link.order_id == first_order.id)
    second_link = next(link for link in links if link.order_id == second_order.id)
    await attachment_session.refresh(first_link)
    await attachment_session.refresh(second_link)
    assert attachments[0].archived_at is None
    assert first_link.archived_at is not None
    assert second_link.archived_at is None
    assert (await ServiceAttachmentService.list_order_attachments(
        attachment_session, order_id=int(first_order.id)
    ))["total"] == 0
    assert (await ServiceAttachmentService.list_order_attachments(
        attachment_session, order_id=int(second_order.id)
    ))["total"] == 1


@pytest.mark.asyncio
async def test_list_order_attachments_dual_reads_normalized_and_unmigrated_legacy_items(
    attachment_session,
):
    storage = FakePrivateAttachmentStorage()
    order = Order(
        title="Legacy service visit",
        technical_meta={
            "telegram_attachments": [
                {
                    "file_id": "already-normalized",
                    "filename": "normalized.pdf",
                    "mime_type": "application/pdf",
                    "purpose": "document",
                    "attached_at": "2026-07-01T10:00:00Z",
                },
                {
                    "file_id": "legacy-only",
                    "filename": "legacy.jpg",
                    "mime_type": "image/jpeg",
                    "purpose": "before_work",
                    "size_bytes": 123,
                    "attached_at": "2026-07-02T11:30:00Z",
                },
            ]
        },
    )
    attachment_session.add(order)
    await attachment_session.commit()

    await ServiceAttachmentService.create_and_link_order_attachment(
        attachment_session,
        order_id=int(order.id),
        content=b"normalized pdf",
        filename="normalized.pdf",
        mime_type="application/pdf",
        category="document",
        telegram_meta={"file_id": "already-normalized"},
        storage=storage,
    )

    result = await ServiceAttachmentService.list_order_attachments(
        attachment_session,
        order_id=int(order.id),
    )

    assert result is not None
    assert result["total"] == 2
    normalized = next(item for item in result["items"] if not item["legacy"])
    legacy = next(item for item in result["items"] if item["legacy"])
    assert normalized["filename"] == "normalized.pdf"
    assert legacy["legacy_key"] == "telegram:1:legacy-only"
    assert legacy["category"] == "before_work"
    assert legacy["processing_status"] == "migration_required"

