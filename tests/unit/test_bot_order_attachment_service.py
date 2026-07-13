import hashlib
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import Customer, Order, OrderAttachmentLink, OrderInstaller, OrderStatus, OrderWorkStage, ServiceAttachment, StaffUser
from services.bot_order_attachment_service import BotOrderAttachmentService
from services.private_attachment_storage_service import StoredPrivateObject


class FakePrivateAttachmentStorage:
    provider_name = "test_private"

    def __init__(self):
        self.calls = []

    async def save(self, **kwargs):
        self.calls.append(kwargs)
        return StoredPrivateObject(
            provider=self.provider_name,
            storage_key=f"private/{kwargs['variant']}/{kwargs['content_hash']}.{kwargs['extension']}",
            content_hash=kwargs["content_hash"],
            size_bytes=len(kwargs["content"]),
        )

    async def read(self, storage_key: str) -> bytes:
        raise FileNotFoundError(storage_key)

    async def presign(self, storage_key: str, *, expires_seconds: int, download_name: str | None = None):
        return None


@pytest.fixture
async def sqlite_order_attachment_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'bot_order_attachment.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_stores_file_id_in_order_meta_and_comment(sqlite_order_attachment_session):
    customer = Customer(name="Иван", phone="+375291234567")
    sqlite_order_attachment_session.add(customer)
    await sqlite_order_attachment_session.flush()
    order = Order(customer_id=customer.id, title="Монтаж", comment="Исходный комментарий")
    sqlite_order_attachment_session.add(order)
    await sqlite_order_attachment_session.commit()

    result = await BotOrderAttachmentService.attach_to_order(
        sqlite_order_attachment_session,
        int(order.id),
        file_id="AgACAgIAAxkBAAIB_photo",
        filename="объект.jpg",
        mime_type="image/jpeg",
        telegram_user_id=777,
        telegram_chat_id=100,
        telegram_message_id=55,
    )

    assert result is not None
    assert result["id"] == order.id
    assert result["already_attached"] is False
    await sqlite_order_attachment_session.refresh(order)
    attachments = order.technical_meta[BotOrderAttachmentService.TELEGRAM_ATTACHMENTS_META_KEY]
    assert attachments == [
        {
            "source": "telegram_bot",
            "file_id": "AgACAgIAAxkBAAIB_photo",
            "filename": "объект.jpg",
            "mime_type": "image/jpeg",
            "kind": "photo",
            "telegram_user_id": 777,
            "telegram_chat_id": 100,
            "telegram_message_id": 55,
            "attached_at": attachments[0]["attached_at"],
        }
    ]
    assert "Исходный комментарий" in order.comment
    assert "file_id=AgACAgIAAxkBAAIB_photo" in order.comment


@pytest.mark.asyncio
async def test_stores_attachment_content_in_private_history(
    sqlite_order_attachment_session,
    monkeypatch,
):
    fake_storage = FakePrivateAttachmentStorage()
    monkeypatch.setattr(
        "services.service_attachment_service.get_private_attachment_storage",
        lambda: fake_storage,
    )
    order = Order(id=121, title="Монтаж")
    sqlite_order_attachment_session.add(order)
    await sqlite_order_attachment_session.commit()

    result = await BotOrderAttachmentService.attach_to_order(
        sqlite_order_attachment_session,
        int(order.id),
        file_id="telegram-photo",
        filename="объект.jpeg",
        mime_type="image/jpeg",
        telegram_user_id=777,
        telegram_chat_id=100,
        telegram_message_id=55,
        content=b"image-content",
    )

    assert result is not None
    digest = hashlib.sha256(b"image-content").hexdigest()
    assert result["attachment"]["storage_provider"] == "private_service_attachment"
    assert fake_storage.calls[0]["variant"] == "original"
    assert fake_storage.calls[0]["content_hash"] == digest
    assert fake_storage.calls[0]["extension"] == "jpg"
    await sqlite_order_attachment_session.refresh(order)
    attachment = order.technical_meta[BotOrderAttachmentService.TELEGRAM_ATTACHMENTS_META_KEY][0]
    assert attachment["storage_provider"] == "private_service_attachment"
    assert attachment["content_hash"] == digest
    assert attachment["size_bytes"] == len(b"image-content")
    assert "url=" not in order.comment
    stored = (await sqlite_order_attachment_session.execute(select(ServiceAttachment))).scalars().one()
    link = (await sqlite_order_attachment_session.execute(select(OrderAttachmentLink))).scalars().one()
    assert stored.storage_provider == "test_private"
    assert stored.telegram_file_id == "telegram-photo"
    assert link.order_id == order.id


@pytest.mark.asyncio
async def test_does_not_duplicate_same_file(sqlite_order_attachment_session):
    order = Order(title="Монтаж")
    sqlite_order_attachment_session.add(order)
    await sqlite_order_attachment_session.commit()

    kwargs = {
        "file_id": "same-file",
        "filename": "акт.pdf",
        "mime_type": "application/pdf",
        "telegram_user_id": 777,
        "telegram_chat_id": 100,
        "telegram_message_id": 55,
    }
    first = await BotOrderAttachmentService.attach_to_order(sqlite_order_attachment_session, int(order.id), **kwargs)
    second = await BotOrderAttachmentService.attach_to_order(sqlite_order_attachment_session, int(order.id), **kwargs)

    assert first["already_attached"] is False
    assert second["already_attached"] is True
    await sqlite_order_attachment_session.refresh(order)
    attachments = order.technical_meta[BotOrderAttachmentService.TELEGRAM_ATTACHMENTS_META_KEY]
    assert len(attachments) == 1
    assert order.comment.count("file_id=same-file") == 1


@pytest.mark.asyncio
async def test_updates_existing_attachment_with_stored_content(
    sqlite_order_attachment_session,
    monkeypatch,
):
    fake_storage = FakePrivateAttachmentStorage()
    monkeypatch.setattr(
        "services.service_attachment_service.get_private_attachment_storage",
        lambda: fake_storage,
    )
    order = Order(
        id=121,
        title="Монтаж",
        technical_meta={
            BotOrderAttachmentService.TELEGRAM_ATTACHMENTS_META_KEY: [
                {
                    "source": "telegram_bot",
                    "file_id": "same-file",
                    "filename": "объект.jpg",
                    "mime_type": "image/jpeg",
                    "kind": "photo",
                    "telegram_user_id": 777,
                    "telegram_chat_id": 100,
                    "telegram_message_id": 55,
                    "attached_at": "2026-07-02T13:39:43",
                }
            ]
        },
    )
    sqlite_order_attachment_session.add(order)
    await sqlite_order_attachment_session.commit()

    result = await BotOrderAttachmentService.attach_to_order(
        sqlite_order_attachment_session,
        int(order.id),
        file_id="same-file",
        filename="объект.jpg",
        mime_type="image/jpeg",
        telegram_user_id=777,
        telegram_chat_id=100,
        telegram_message_id=55,
        content=b"image-content",
    )

    assert result is not None
    assert result["already_attached"] is True
    digest = hashlib.sha256(b"image-content").hexdigest()
    assert result["attachment"]["storage_provider"] == "private_service_attachment"
    await sqlite_order_attachment_session.refresh(order)
    attachments = order.technical_meta[BotOrderAttachmentService.TELEGRAM_ATTACHMENTS_META_KEY]
    assert len(attachments) == 1
    assert "url" not in attachments[0]
    assert attachments[0]["storage_provider"] == "private_service_attachment"
    assert attachments[0]["content_hash"] == digest
    stored = (await sqlite_order_attachment_session.execute(select(ServiceAttachment))).scalars().one()
    assert stored.telegram_file_id == "same-file"


@pytest.mark.asyncio
async def test_lists_recent_active_orders(sqlite_order_attachment_session):
    active = Order(title="Активный", status=OrderStatus.NEGOTIATION)
    closed = Order(title="Закрытый", status=OrderStatus.CLOSED)
    sqlite_order_attachment_session.add(active)
    sqlite_order_attachment_session.add(closed)
    await sqlite_order_attachment_session.commit()

    orders = await BotOrderAttachmentService.list_recent_orders(sqlite_order_attachment_session)

    assert [item["id"] for item in orders] == [active.id]


@pytest.mark.asyncio
async def test_executor_can_attach_only_assigned_order(sqlite_order_attachment_session):
    staff = StaffUser(
        display_name="Монтажник",
        status="active",
        primary_role="installer",
        roles=["installer"],
        telegram_id=777,
        legacy_installer_id=10,
    )
    assigned = Order(title="Назначенный")
    other = Order(title="Чужой")
    sqlite_order_attachment_session.add(staff)
    sqlite_order_attachment_session.add(assigned)
    sqlite_order_attachment_session.add(other)
    await sqlite_order_attachment_session.flush()
    sqlite_order_attachment_session.add(OrderWorkStage(order_id=assigned.id, installer_id=10, name="Монтаж"))
    await sqlite_order_attachment_session.commit()

    assert await BotOrderAttachmentService.can_attach_to_order(
        sqlite_order_attachment_session,
        int(assigned.id),
        telegram_user_id=777,
    )
    assert not await BotOrderAttachmentService.can_attach_to_order(
        sqlite_order_attachment_session,
        int(other.id),
        telegram_user_id=777,
    )


@pytest.mark.asyncio
async def test_executor_can_attach_legacy_installer_order(sqlite_order_attachment_session):
    staff = StaffUser(
        display_name="Монтажник",
        status="active",
        primary_role="installer",
        roles=["installer"],
        telegram_id=777,
        legacy_installer_id=10,
    )
    order = Order(title="Старый монтаж")
    sqlite_order_attachment_session.add(staff)
    sqlite_order_attachment_session.add(order)
    await sqlite_order_attachment_session.flush()
    sqlite_order_attachment_session.add(OrderInstaller(order_id=order.id, installer_id=10))
    await sqlite_order_attachment_session.commit()

    assert await BotOrderAttachmentService.can_attach_to_order(
        sqlite_order_attachment_session,
        int(order.id),
        telegram_user_id=777,
    )


@pytest.mark.asyncio
async def test_manager_can_attach_any_order(sqlite_order_attachment_session):
    assert await BotOrderAttachmentService.can_attach_to_order(
        sqlite_order_attachment_session,
        999,
        telegram_user_id=None,
        can_attach_any=True,
    )
