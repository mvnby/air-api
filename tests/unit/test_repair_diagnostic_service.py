from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import IntegrationOutboxEvent, LeadSource, Order, OrderStatus
from services.bot_service import BotService
from services.general_media_storage_service import StoredGeneralMediaObject
from services.repair_diagnostic_service import (
    MAX_PAYLOAD_BYTES,
    MAX_PHOTO_BYTES,
    RepairDiagnosticIncomingFile,
    RepairDiagnosticLeadPayload,
    RepairDiagnosticService,
)
from services.repair_diagnostic_intake_service import RepairDiagnosticIntakeService
from services.repair_diagnostic_ai_job_service import (
    REPAIR_DIAGNOSTIC_AI_REQUESTED_EVENT,
    RepairDiagnosticAiJobService,
)
from services.staff_user_service import StaffUserService


class FakeRepairDiagnosticStorage:
    provider_name = "local"

    def __init__(self):
        self.save_calls = []
        self.delete_calls = []

    async def save_media(self, **kwargs):
        self.save_calls.append(kwargs)
        variant_type = kwargs["variant_type"]
        extension = kwargs["extension"]
        return StoredGeneralMediaObject(
            url=f"/media/orders/42/repair-diagnostic/{variant_type}/hash.{extension}",
            content_hash="c" * 64,
            storage_provider="local",
            path=f"media/orders/42/repair-diagnostic/{variant_type}/hash.{extension}",
            size_bytes=len(kwargs["content"]),
        )

    async def delete_media(self, path):
        self.delete_calls.append(path)

    async def read_media(self, path):
        return path.encode()


class SizedFakeUpload:
    filename = "photo.png"
    content_type = "image/png"

    def __init__(self, content: bytes):
        self.content = content
        self.read_sizes = []

    async def read(self, size=-1):
        self.read_sizes.append(size)
        return self.content[:size] if size >= 0 else self.content


@pytest.fixture
async def sqlite_repair_diagnostic_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'repair_diagnostic.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_repair_diagnostic_service_creates_repair_order_with_structured_meta(
    sqlite_repair_diagnostic_session,
    monkeypatch,
    tenant_scope,
):
    storage = FakeRepairDiagnosticStorage()
    monkeypatch.setattr(
        "services.repair_diagnostic_intake_service.get_general_media_storage",
        lambda: storage,
    )
    payload = RepairDiagnosticLeadPayload.model_validate(
        {
            "scenario": "repair",
            "symptom": "not_cooling",
            "problem_timing": "after_minutes",
            "symptom_details": {
                "indoor_fan_works": "yes",
                "outdoor_unit_starts": "unknown",
                "freezing_seen": "no",
                "cooled_before": "yes",
            },
            "client_checks": ["filters_cleaned", "power_restarted"],
            "client_comment": "Стал хуже холодить после жары",
            "contact": {
                "name": "Анна",
                "phone": "+375291112233",
                "address": "Витебск, центр",
            },
        }
    )
    uploads = {
        "nameplate": [
            RepairDiagnosticIncomingFile(
                filename="nameplate.jpg",
                content_type="image/jpeg",
                content=b"nameplate-content",
            )
        ],
        "indoor_unit": [
            RepairDiagnosticIncomingFile(
                filename="indoor.png",
                content_type="image/png",
                content=b"indoor-content",
            )
        ],
    }

    response, nameplate_files, replayed = await RepairDiagnosticIntakeService.create_lead(
        sqlite_repair_diagnostic_session,
        payload=payload,
        uploads=uploads,
        tenant_scope=tenant_scope,
        idempotency_key="repair-request-unit-0001",
    )

    assert response.status == "new_lead"
    assert response.ai_pre_diagnosis_status == "pending"
    assert len(nameplate_files) == 1
    assert replayed is False
    replay_response, _, replayed = await RepairDiagnosticIntakeService.create_lead(
        sqlite_repair_diagnostic_session,
        payload=payload,
        uploads=uploads,
        tenant_scope=tenant_scope,
        idempotency_key="repair-request-unit-0001",
    )
    assert replayed is True
    assert replay_response == response
    assert len(storage.save_calls) == 2
    assert all(
        call["namespace"].startswith("public-write/1/1/repair-diagnostic/")
        for call in storage.save_calls
    )

    order = await sqlite_repair_diagnostic_session.get(Order, response.order_id)
    assert order is not None
    assert order.status == OrderStatus.NEW_LEAD
    assert order.lead_source == LeadSource.SITE
    assert order.tenant_id == tenant_scope.tenant_id
    assert order.storefront_id == tenant_scope.storefront_id
    assert order.workflow_type == "repair"
    assert order.delivery_address == "Витебск, центр"
    assert order.title == "Ремонт кондиционера: Не охлаждает / слабо охлаждает"

    meta = order.technical_meta
    assert meta["service_type"] == "repair"
    repair_meta = meta["repair"]
    assert repair_meta["scenario"] == "repair"
    assert repair_meta["symptom"] == "not_cooling"
    assert repair_meta["symptom_details"]["outdoor_unit_starts"] == "unknown"
    assert repair_meta["client_checks"] == ["filters_cleaned", "power_restarted"]
    assert repair_meta["photos"]["nameplate"][0]["content_hash"] == "c" * 64
    assert repair_meta["ai_pre_diagnosis_status"] == "pending"
    assert repair_meta["preliminary_fault_type"] == "refrigerant_leak"
    assert "Фото шильдика" not in repair_meta["missing_data"]

    events = list(
        (
            await sqlite_repair_diagnostic_session.execute(
                select(IntegrationOutboxEvent).where(
                    IntegrationOutboxEvent.event_type
                    == REPAIR_DIAGNOSTIC_AI_REQUESTED_EVENT
                )
            )
        ).scalars()
    )
    assert len(events) == 1
    assert events[0].status == "pending"
    assert events[0].payload == {
        "order_id": response.order_id,
        "tenant_id": tenant_scope.tenant_id,
        "storefront_id": tenant_scope.storefront_id,
    }
    assert events[0].idempotency_key is not None
    assert events[0].idempotency_key.startswith("repair-diagnostic-ai:")
    assert payload.contact.phone not in events[0].idempotency_key

    # Simulate a worker/process crash after the durable claim committed.
    events[0].status = "processing"
    events[0].worker_id = "crashed-worker"
    events[0].lease_token = "expired-lease"
    events[0].lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    events[0].attempts = 1
    sqlite_repair_diagnostic_session.add(events[0])
    await sqlite_repair_diagnostic_session.commit()

    runner_calls = []

    async def runner(**kwargs):
        runner_calls.append(kwargs)

    worker_factory = sessionmaker(
        bind=sqlite_repair_diagnostic_session.bind,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    processed = await RepairDiagnosticAiJobService.process_batch(
        worker_id="unit-repair-ai",
        session_factory=worker_factory,
        runner=runner,
    )
    assert processed == 1
    assert runner_calls == [
        {"order_id": response.order_id, "tenant_id": tenant_scope.tenant_id}
    ]
    await sqlite_repair_diagnostic_session.refresh(events[0])
    assert events[0].status == "published"
    assert events[0].attempts == 2


@pytest.mark.asyncio
async def test_repair_diagnostic_aggregate_upload_boundary(monkeypatch):
    monkeypatch.setattr(
        "services.repair_diagnostic_service._validate_photo",
        lambda **_kwargs: None,
    )
    first = SizedFakeUpload(b"a" * (MAX_PAYLOAD_BYTES // 2))
    exact = SizedFakeUpload(b"b" * (MAX_PAYLOAD_BYTES // 2))

    uploads = await RepairDiagnosticService.collect_uploads(
        {"nameplate": [first], "indoor_unit": [exact]}
    )
    assert sum(
        len(item.content)
        for group in uploads.values()
        for item in group
    ) == MAX_PAYLOAD_BYTES
    assert first.read_sizes == [MAX_PHOTO_BYTES + 1]

    overflow = SizedFakeUpload(b"c" * (MAX_PAYLOAD_BYTES // 2 + 1))
    with pytest.raises(ValueError, match="18 МБ"):
        await RepairDiagnosticService.collect_uploads(
            {"nameplate": [first], "indoor_unit": [overflow]}
        )


@pytest.mark.asyncio
async def test_repair_notification_escapes_contact_fields(
    monkeypatch,
    caplog,
    tenant_scope,
):
    payload = RepairDiagnosticLeadPayload.model_validate(
        {
            "scenario": "repair",
            "symptom": "not_cooling",
            "client_checks": [],
            "contact": {
                "name": "Анна <admin>",
                "phone": "+375291112233",
                "address": "Витебск & <центр>",
            },
        }
    )
    sent_messages = []

    async def fake_recipients(_session, *, tenant_scope):
        return [101, 202]

    async def fake_send_message(admin_id, text):
        sent_messages.append((admin_id, text))
        return admin_id == 101

    monkeypatch.setattr(
        StaffUserService,
        "get_active_owner_admin_telegram_recipient_ids",
        fake_recipients,
    )
    monkeypatch.setattr(BotService, "send_message", fake_send_message)

    with caplog.at_level("WARNING"):
        await RepairDiagnosticService._notify_admins(
            object(),
            SimpleNamespace(id=42),
            payload,
            {},
            tenant_scope=tenant_scope,
        )

    sent_text = sent_messages[0][1]
    assert "Анна &lt;admin&gt;" in sent_text
    assert "Витебск &amp; &lt;центр&gt;" in sent_text
    assert "<admin>" not in sent_text
    assert len(sent_text) <= BotService.MAX_MESSAGE_LENGTH
    assert "REPAIR_DIAGNOSTIC_NOTIFY_DELIVERY_FAILED order_id=42 admin_id=202" in caplog.text
