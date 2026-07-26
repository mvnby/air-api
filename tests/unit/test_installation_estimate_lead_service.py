import io
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, func, select

from models import (
    IntegrationOutboxEvent,
    Order,
    OrderAttachmentLink,
    ServiceAttachment,
)
from schemas_installation_estimate import InstallationEstimateLeadPayload
from services.communications.outbox_service import IntegrationOutboxService
from services.installation_estimate_lead_service import (
    InstallationEstimateIdempotencyConflict,
    InstallationEstimateIncomingFile,
    InstallationEstimateLeadService,
)
from services.private_attachment_storage_service import StoredPrivateObject
from services.order_service import OrderService
from services.service_attachment_service import ServiceAttachmentService


def _png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (24, 24), color=(20, 150, 140)).save(output, format="PNG")
    return output.getvalue()


class FakePrivateStorage:
    provider_name = "local"

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    async def save(self, *, content, content_hash, extension, content_type, variant):
        key = f"service-attachments/{content_hash}/{variant}.{extension}"
        self.objects[key] = content
        return StoredPrivateObject(
            provider=self.provider_name,
            storage_key=key,
            content_hash=content_hash,
            size_bytes=len(content),
        )

    async def read(self, storage_key):
        return self.objects[storage_key]

    async def exists(self, storage_key):
        return storage_key in self.objects

    async def delete(self, storage_key):
        self.objects.pop(storage_key, None)

    async def verify_writable(self):
        return None

    async def presign(self, storage_key, *, expires_seconds, download_name=None):
        return None


class FakeUpload:
    filename = "photo.png"
    content_type = "image/png"

    async def read(self, size=-1):
        return _png_bytes()


@pytest.fixture
async def installation_estimate_session(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'installation-estimate.db'}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _payload(**overrides) -> InstallationEstimateLeadPayload:
    return InstallationEstimateLeadPayload.model_validate(
        {
            "name": "Анна",
            "phone": "+375291112233",
            "email": "anna@example.com",
            "address": "Минск, ул. Ленина, 1",
            "description": "Внутренний блок над окном",
            "object_type": "apartment",
            "consent": True,
            **overrides,
        }
    )


def _upload(content: bytes | None = None) -> InstallationEstimateIncomingFile:
    content = content or _png_bytes()
    import hashlib

    return InstallationEstimateIncomingFile(
        category="indoor_unit",
        filename="indoor.png",
        content_type="image/png",
        content=content,
        content_hash=hashlib.sha256(content).hexdigest(),
    )


@pytest.mark.asyncio
async def test_installation_estimate_is_atomic_private_and_idempotent(
    installation_estimate_session,
):
    storage = FakePrivateStorage()
    payload = _payload()
    uploads = [_upload()]

    created = await InstallationEstimateLeadService.create_lead(
        installation_estimate_session,
        payload=payload,
        uploads=uploads,
        idempotency_key="estimate-request-0001",
        storage=storage,
    )
    replayed = await InstallationEstimateLeadService.create_lead(
        installation_estimate_session,
        payload=payload,
        uploads=uploads,
        idempotency_key="estimate-request-0001",
        storage=storage,
    )

    assert created.replayed is False
    assert replayed.replayed is True
    assert replayed.order_id == created.order_id
    assert replayed.attachment_count == 1

    order = await installation_estimate_session.get(Order, created.order_id)
    assert order is not None
    assert order.source_fingerprint
    assert order.technical_meta["service_type"] == "pre_install"
    assert order.technical_meta["installation_estimate"]["status"] == "pending_review"
    assert order.technical_meta["installation_estimate"]["attachment_policy"] == "private_access_only"

    attachments = list(
        (
            await installation_estimate_session.execute(select(ServiceAttachment))
        ).scalars()
    )
    links = list(
        (
            await installation_estimate_session.execute(select(OrderAttachmentLink))
        ).scalars()
    )
    assert len(attachments) == 1
    assert len(links) == 1
    assert links[0].category == "installation_indoor"
    assert attachments[0].source == "website_installation_estimate"
    assert attachments[0].source_meta["photo_category"] == "indoor_unit"
    assert not attachments[0].storage_key.startswith("http")
    manager_attachments = await ServiceAttachmentService.list_order_attachments(
        installation_estimate_session,
        order_id=created.order_id,
    )
    assert manager_attachments is not None
    assert manager_attachments["total"] == 1
    inbox = await OrderService.get_leads_inbox(installation_estimate_session)
    assert inbox.items[0].attachment_count == 1
    assert (
        await installation_estimate_session.scalar(
            select(func.count(IntegrationOutboxEvent.event_id))
        )
        == 1
    )


@pytest.mark.asyncio
async def test_installation_estimate_rejects_reused_key_with_different_request(
    installation_estimate_session,
):
    storage = FakePrivateStorage()
    await InstallationEstimateLeadService.create_lead(
        installation_estimate_session,
        payload=_payload(),
        uploads=[_upload()],
        idempotency_key="estimate-request-0002",
        storage=storage,
    )

    with pytest.raises(
        InstallationEstimateIdempotencyConflict,
        match="другой заявки",
    ):
        await InstallationEstimateLeadService.create_lead(
            installation_estimate_session,
            payload=_payload(description="Другая заявка"),
            uploads=[_upload()],
            idempotency_key="estimate-request-0002",
            storage=storage,
        )


@pytest.mark.asyncio
async def test_installation_estimate_rolls_back_db_and_private_objects(
    installation_estimate_session,
    monkeypatch,
):
    storage = FakePrivateStorage()

    async def fail_enqueue(*args, **kwargs):
        raise RuntimeError("outbox unavailable")

    monkeypatch.setattr(IntegrationOutboxService, "enqueue", fail_enqueue)

    with pytest.raises(RuntimeError, match="outbox unavailable"):
        await InstallationEstimateLeadService.create_lead(
            installation_estimate_session,
            payload=_payload(),
            uploads=[_upload()],
            idempotency_key="estimate-request-0003",
            storage=storage,
        )

    assert (
        await installation_estimate_session.scalar(select(func.count(Order.id)))
        == 0
    )
    assert (
        await installation_estimate_session.scalar(
            select(func.count(ServiceAttachment.id))
        )
        == 0
    )
    assert storage.objects == {}


@pytest.mark.asyncio
async def test_installation_estimate_enforces_per_category_file_limit():
    with pytest.raises(ValueError, match="не больше 5"):
        await InstallationEstimateLeadService.collect_uploads(
            {"indoor_unit": [FakeUpload() for _ in range(6)]}
        )
