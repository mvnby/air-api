import hashlib
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import (
    Customer,
    CustomerEquipment,
    EquipmentAttachmentLink,
    EquipmentServiceHistory,
    Order,
    OrderAttachmentLink,
    ServiceAttachment,
)
from services.private_attachment_storage_service import StoredPrivateObject
from services.service_attachment_presenter import legacy_attachment_source_key
from services.service_attachment_service import ServiceAttachmentService


class FakePrivateAttachmentStorage:
    provider_name = "test_private"

    def __init__(self) -> None:
        self.saved: list[dict] = []
        self.objects: dict[str, bytes] = {}

    async def save(self, **kwargs) -> StoredPrivateObject:
        self.saved.append(kwargs)
        stored = StoredPrivateObject(
            provider=self.provider_name,
            storage_key=f"private/{kwargs['content_hash']}/{kwargs['variant']}.{kwargs['extension']}",
            content_hash=kwargs["content_hash"],
            size_bytes=len(kwargs["content"]),
        )
        self.objects.setdefault(stored.storage_key, kwargs["content"])
        return stored

    async def read(self, storage_key: str) -> bytes:
        try:
            return self.objects[storage_key]
        except KeyError as exc:
            raise FileNotFoundError(storage_key) from exc

    async def exists(self, storage_key: str) -> bool:
        return storage_key in self.objects

    async def delete(self, storage_key: str) -> None:
        self.objects.pop(storage_key, None)

    async def verify_writable(self) -> None:
        return None

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
async def test_private_attachment_dedupes_binary_without_merging_business_occurrences(attachment_session):
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
    assert first["id"] != second["id"]
    assert len(attachments) == 2
    assert len(links) == 2
    assert len(storage.saved) == 1
    assert {item.content_hash for item in attachments} == {hashlib.sha256(content).hexdigest()}
    assert {item.storage_provider for item in attachments} == {"test_private"}
    assert len({item.storage_key for item in attachments}) == 1
    assert {item.original_filename for item in attachments} == {"report.txt", "same-content.txt"}

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
    first_attachment = next(item for item in attachments if item.id == first["id"])
    second_attachment = next(item for item in attachments if item.id == second["id"])
    await attachment_session.refresh(first_attachment)
    await attachment_session.refresh(second_attachment)
    first_link = next(link for link in links if link.order_id == first_order.id)
    second_link = next(link for link in links if link.order_id == second_order.id)
    await attachment_session.refresh(first_link)
    await attachment_session.refresh(second_link)
    assert first_attachment.archived_at is not None
    assert second_attachment.archived_at is None
    assert first_link.archived_at is not None
    assert second_link.archived_at is None
    assert (await ServiceAttachmentService.list_order_attachments(
        attachment_session, order_id=int(first_order.id)
    ))["total"] == 0
    assert (await ServiceAttachmentService.list_order_attachments(
        attachment_session, order_id=int(second_order.id)
    ))["total"] == 1
    assert await ServiceAttachmentService.get_access(
        attachment_session,
        attachment_id=first["id"],
        variant="original",
        download=False,
        storage=storage,
    ) is None


@pytest.mark.asyncio
async def test_telegram_occurrence_is_idempotent_but_a_new_message_keeps_its_own_record(attachment_session):
    storage = FakePrivateAttachmentStorage()
    order = Order(title="Telegram evidence")
    attachment_session.add(order)
    await attachment_session.commit()
    common = {
        "order_id": int(order.id),
        "content": b"same telegram image",
        "filename": "plate.jpg",
        "mime_type": "image/jpeg",
        "category": "nameplate",
        "storage": storage,
    }

    first = await ServiceAttachmentService.create_and_link_order_attachment(
        attachment_session,
        **common,
        telegram_meta={"file_id": "file-a", "chat_id": 10, "message_id": 20},
    )
    retry = await ServiceAttachmentService.create_and_link_order_attachment(
        attachment_session,
        **common,
        telegram_meta={"file_id": "file-a", "chat_id": 10, "message_id": 20},
    )
    second_message = await ServiceAttachmentService.create_and_link_order_attachment(
        attachment_session,
        **common,
        telegram_meta={"file_id": "file-a", "chat_id": 10, "message_id": 21},
    )

    assert retry["id"] == first["id"]
    assert second_message["id"] != first["id"]
    attachments = list((await attachment_session.execute(select(ServiceAttachment))).scalars().all())
    assert len(attachments) == 2
    assert {item.telegram_message_id for item in attachments} == {20, 21}
    assert len(storage.saved) == 1


@pytest.mark.asyncio
async def test_identical_evidence_does_not_cross_link_equipment_between_customers(attachment_session):
    storage = FakePrivateAttachmentStorage()
    first_customer = Customer(name="First customer", phone="+375290000001")
    second_customer = Customer(name="Second customer", phone="+375290000002")
    attachment_session.add_all([first_customer, second_customer])
    await attachment_session.flush()
    first_order = Order(title="First order", customer_id=int(first_customer.id))
    second_order = Order(title="Second order", customer_id=int(second_customer.id))
    first_equipment = CustomerEquipment(customer_id=int(first_customer.id), display_name="First system")
    second_equipment = CustomerEquipment(customer_id=int(second_customer.id), display_name="Second system")
    attachment_session.add_all([first_order, second_order, first_equipment, second_equipment])
    await attachment_session.commit()

    for order, equipment, message_id in (
        (first_order, first_equipment, 31),
        (second_order, second_equipment, 32),
    ):
        await ServiceAttachmentService.create_and_link_order_attachment(
            attachment_session,
            order_id=int(order.id),
            equipment_id=int(equipment.id),
            content=b"same nameplate bytes",
            filename="nameplate.jpg",
            mime_type="image/jpeg",
            category="nameplate",
            telegram_meta={"file_id": f"file-{message_id}", "chat_id": 10, "message_id": message_id},
            storage=storage,
        )

    first_result = await ServiceAttachmentService.list_order_attachments(
        attachment_session,
        order_id=int(first_order.id),
    )
    second_result = await ServiceAttachmentService.list_order_attachments(
        attachment_session,
        order_id=int(second_order.id),
    )
    assert first_result is not None and first_result["items"][0]["equipment_id"] == first_equipment.id
    assert second_result is not None and second_result["items"][0]["equipment_id"] == second_equipment.id
    assert len(storage.saved) == 1


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


@pytest.mark.asyncio
async def test_url_only_legacy_item_is_not_duplicated_after_private_migration(attachment_session):
    storage = FakePrivateAttachmentStorage()
    raw = {
        "url": "https://mvn.by/media/legacy/result.jpg",
        "filename": "result.jpg",
        "mime_type": "image/jpeg",
        "purpose": "installation_result",
    }
    order = Order(title="URL-only evidence", technical_meta={"telegram_attachments": [raw]})
    attachment_session.add(order)
    await attachment_session.commit()

    await ServiceAttachmentService.create_and_link_order_attachment(
        attachment_session,
        order_id=int(order.id),
        content=b"private result",
        filename="result.jpg",
        mime_type="image/jpeg",
        category="installation_result",
        telegram_meta={
            "source_meta": {
                "legacy_source_key": legacy_attachment_source_key(int(order.id), raw),
            }
        },
        storage=storage,
    )

    result = await ServiceAttachmentService.list_order_attachments(
        attachment_session,
        order_id=int(order.id),
    )
    count = await ServiceAttachmentService.order_attachment_count(
        attachment_session,
        order=order,
    )

    assert result is not None
    assert result["total"] == 1
    assert result["items"][0]["legacy"] is False
    assert count == 1


@pytest.mark.asyncio
async def test_attachment_can_follow_an_equipment_service_history_event(attachment_session):
    storage = FakePrivateAttachmentStorage()
    customer = Customer(name="Service customer", phone="+375290000003")
    attachment_session.add(customer)
    await attachment_session.flush()
    order = Order(title="Maintenance visit", customer_id=int(customer.id))
    equipment = CustomerEquipment(customer_id=int(customer.id), display_name="Living room AC")
    attachment_session.add_all([order, equipment])
    await attachment_session.flush()
    history = EquipmentServiceHistory(
        equipment_id=int(equipment.id),
        order_id=int(order.id),
        notes="Annual maintenance",
    )
    attachment_session.add(history)
    await attachment_session.commit()

    created = await ServiceAttachmentService.create_and_link_order_attachment(
        attachment_session,
        order_id=int(order.id),
        service_history_id=int(history.id),
        content=b"maintenance evidence",
        filename="maintenance.txt",
        mime_type="text/plain",
        category="service",
        storage=storage,
    )

    assert created["equipment_id"] == equipment.id
    assert created["service_history_id"] == history.id
    equipment_link = (
        await attachment_session.execute(
            select(EquipmentAttachmentLink).where(
                EquipmentAttachmentLink.attachment_id == int(created["id"])
            )
        )
    ).scalars().one()
    assert equipment_link.equipment_id == equipment.id
    assert equipment_link.service_history_id == history.id

    updated = await ServiceAttachmentService.update_attachment(
        attachment_session,
        attachment_id=int(created["id"]),
        order_id=int(order.id),
        payload={"service_history_id": None},
    )
    assert updated is not None
    assert updated["equipment_id"] == equipment.id
    assert updated["service_history_id"] is None


@pytest.mark.asyncio
async def test_attachment_rejects_service_history_from_another_order(attachment_session):
    storage = FakePrivateAttachmentStorage()
    customer = Customer(name="Another customer", phone="+375290000004")
    attachment_session.add(customer)
    await attachment_session.flush()
    first_order = Order(title="First visit", customer_id=int(customer.id))
    second_order = Order(title="Second visit", customer_id=int(customer.id))
    equipment = CustomerEquipment(customer_id=int(customer.id), display_name="Office AC")
    attachment_session.add_all([first_order, second_order, equipment])
    await attachment_session.flush()
    history = EquipmentServiceHistory(
        equipment_id=int(equipment.id),
        order_id=int(first_order.id),
    )
    attachment_session.add(history)
    await attachment_session.commit()

    with pytest.raises(ValueError, match="does not belong to this order"):
        await ServiceAttachmentService.create_and_link_order_attachment(
            attachment_session,
            order_id=int(second_order.id),
            service_history_id=int(history.id),
            content=b"wrong visit evidence",
            filename="wrong.txt",
            mime_type="text/plain",
            storage=storage,
        )
