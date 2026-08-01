"""End-to-end durable delivery contract for installation-estimate intake.

The test deliberately starts at the public multipart endpoint and drives the
same outbox dispatcher and delivery worker used in production.  External
storage and Telegram are replaced only at their provider boundaries.
"""

from __future__ import annotations

import asyncio
import io
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from core.database import get_session
from main import app
from models import (
    CommunicationDelivery,
    CommunicationDeliveryAttempt,
    ConsumerInbox,
    IntegrationOutboxEvent,
    Order,
    StaffUser,
    Storefront,
    Tenant,
)
from services.communications.delivery_worker import CommunicationDeliveryWorker
from services.communications.dispatcher import CommunicationOutboxDispatcher
from services.communications.processing_scope import CommunicationProcessingScope
from services.communications.providers.base import ProviderDeliveryResult
from services.communications.template_registry import (
    CONSUMER_NAME,
    INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
)
from services.private_attachment_storage_service import StoredPrivateObject


def _png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (24, 24), color=(20, 150, 140)).save(output, format="PNG")
    return output.getvalue()


class FakePrivateStorage:
    provider_name = "local"
    inventory_id = "installation-e2e-private"

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def save(self, *, content, content_hash, extension, content_type, variant):
        key = f"private/{content_hash}/{variant}.{extension}"
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


class FakeTelegramProvider:
    channel = "telegram"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def send(self, *, destination: str, text: str, delivery_id: str):
        self.calls.append((destination, text, delivery_id))
        return ProviderDeliveryResult.sent(f"fake-telegram-ack-{len(self.calls)}")

    async def close(self) -> None:
        return None


@pytest.fixture
async def installation_estimate_e2e_session_factory(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'installation-estimate-e2e.sqlite3'}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_installation_estimate_public_intake_is_materialized_and_sent_once_per_recipient(
    installation_estimate_e2e_session_factory,
    monkeypatch,
    caplog,
):
    """A replayed public intake must never duplicate durable delivery or send."""

    storage = FakePrivateStorage()
    monkeypatch.setattr(
        "services.installation_estimate_lead_service.get_private_attachment_storage",
        lambda: storage,
    )
    session_factory = installation_estimate_e2e_session_factory
    async with session_factory() as session:
        tenant = Tenant(
            id=1,
            slug="mvn",
            display_name="Мастер Воздуха",
            kind="operator",
            status="active",
            is_system=True,
        )
        storefront = Storefront(
            id=1,
            tenant_id=1,
            slug="main",
            display_name="MVN",
            status="active",
            is_default=True,
        )
        recipients = [
            StaffUser(
                display_name="E2E owner one",
                status="active",
                roles=["owner"],
                primary_role="owner",
                telegram_id=990001,
            ),
            StaffUser(
                display_name="E2E owner two",
                status="active",
                roles=["owner"],
                primary_role="owner",
                telegram_id=990002,
            ),
        ]
        session.add_all([tenant, storefront, *recipients])
        await session.commit()

    form = {
        "name": "Анна",
        "phone": "+375291112233",
        "email": "anna@example.com",
        "address": "Минск, ул. Ленина, 1",
        "description": "Нужно оценить трассу",
        "object_type": "apartment",
        "consent": "true",
    }
    idempotency_key = "installation-estimate-e2e-request-0001"

    async def override_get_session():
        async with session_factory() as session:
            yield session

    previous_override = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = override_get_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            first_response = await client.post(
                "/api/v1/leads/installation-estimate",
                data=form,
                files=[("indoor_unit", ("indoor.png", _png_bytes(), "image/png"))],
                headers={"Idempotency-Key": idempotency_key},
            )
            replay_response = await client.post(
                "/api/v1/leads/installation-estimate",
                data=form,
                files=[("indoor_unit", ("indoor.png", _png_bytes(), "image/png"))],
                headers={"Idempotency-Key": idempotency_key},
            )
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_session, None)
        else:
            app.dependency_overrides[get_session] = previous_override

    assert first_response.status_code == 200, first_response.text
    assert replay_response.status_code == 200, replay_response.text
    first = first_response.json()
    replay = replay_response.json()
    assert first["replayed"] is False
    assert replay["replayed"] is True
    assert replay["order_id"] == first["order_id"]

    async with session_factory() as session:
        order_count = await session.scalar(select(func.count(Order.id)))
        events = list(
            (
                await session.execute(
                    select(IntegrationOutboxEvent).where(
                        IntegrationOutboxEvent.event_type
                        == INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT
                    )
                )
            ).scalars()
        )
        assert order_count == 1
        order = await session.get(Order, first["order_id"])
        assert order is not None
        assert order.tenant_id == 1
        assert order.storefront_id == 1
        assert len(events) == 1
        event = events[0]
        assert event.aggregate_id == str(first["order_id"])
        assert event.status == "pending"

        scope = CommunicationProcessingScope.all(
            control_revision=0,
            event_created_at_watermark=datetime(
                2000, 1, 1, tzinfo=timezone.utc
            ),
        )
        materialized = await CommunicationOutboxDispatcher.dispatch_next(
            session,
            dispatcher_id="installation-estimate-e2e-dispatcher",
            scope=scope,
        )
        assert materialized is not None
        assert materialized.outcome == "materialized"
        assert materialized.event_id == event.event_id
        assert materialized.delivery_count == 2
        await session.commit()

        deliveries = list(
            (
                await session.execute(
                    select(CommunicationDelivery).where(
                        CommunicationDelivery.event_id == event.event_id
                    )
                )
            ).scalars()
        )
        assert len(deliveries) == 2
        delivery_ids = {delivery.delivery_id for delivery in deliveries}
        assert {delivery.destination for delivery in deliveries} == {"990001", "990002"}
        assert {delivery.status for delivery in deliveries} == {"queued"}
        assert await session.get(ConsumerInbox, (CONSUMER_NAME, event.event_id)) is not None

    provider = FakeTelegramProvider()
    worker = CommunicationDeliveryWorker(
        session_factory=session_factory,
        provider=provider,
        worker_id="installation-estimate-e2e-worker",
        scope=scope,
        lease_seconds=60,
    )

    # SQLite's CURRENT_TIMESTAMP is second-precision, while materialization
    # records a Python timestamp with microseconds.  Let its database clock
    # cross that boundary; PostgreSQL production clocks are microsecond-safe.
    await asyncio.sleep(1.05)
    sent = [await worker.run_once(), await worker.run_once()]
    idle = await worker.run_once()

    assert {outcome.outcome for outcome in sent} == {"sent"}
    assert {outcome.delivery_id for outcome in sent} == delivery_ids
    assert idle.outcome == "idle"
    assert len(provider.calls) == 2
    assert {call[0] for call in provider.calls} == {"990001", "990002"}
    assert {call[2] for call in provider.calls} == delivery_ids
    for _, text, _ in provider.calls:
        assert "<b>МОНТАЖ ПО ФОТО #1</b>" in text
        assert "🖼 Фото: 1" in text

    # The complete intake, materialization and worker log path must not expose
    # customer data or Telegram destinations. Delivery state remains private.
    for pii in ("Анна", "+375291112233", "Минск, ул. Ленина, 1", "990001", "990002"):
        assert pii not in caplog.text

    async with session_factory() as session:
        deliveries = list(
            (
                await session.execute(
                    select(CommunicationDelivery).where(
                        CommunicationDelivery.delivery_id.in_(delivery_ids)
                    )
                )
            ).scalars()
        )
        assert len(deliveries) == 2
        assert {delivery.status for delivery in deliveries} == {"sent"}
        assert {delivery.attempts for delivery in deliveries} == {1}
        assert {delivery.provider_message_id for delivery in deliveries} == {
            "fake-telegram-ack-1",
            "fake-telegram-ack-2",
        }
        for delivery in deliveries:
            attempt = await session.get(
                CommunicationDeliveryAttempt,
                (delivery.delivery_id, 1),
            )
            assert attempt is not None
            assert attempt.outcome == "sent"
