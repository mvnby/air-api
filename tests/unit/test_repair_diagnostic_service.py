import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import (
    IntegrationOutboxEvent,
    LeadSource,
    Order,
    OrderAttachmentLink,
    OrderStatus,
    ServiceAttachment,
)
from services.bot_service import BotService
from services.private_attachment_storage_service import StoredPrivateObject
from services.repair_diagnostic_ai_job_service import (
    REPAIR_DIAGNOSTIC_AI_REQUESTED_EVENT,
    RepairDiagnosticAiJobService,
)
from services.repair_diagnostic_intake_service import RepairDiagnosticIntakeService
from services.repair_diagnostic_service import (
    MAX_PAYLOAD_BYTES,
    MAX_PHOTO_BYTES,
    RepairDiagnosticIncomingFile,
    RepairDiagnosticLeadPayload,
    RepairDiagnosticService,
)
from services.service_attachment_service import ServiceAttachmentService
from services.staff_user_service import StaffUserService
from services.tenant_scope_service import TenantScope


@dataclass
class FakePrivateStorage:
    provider_name: str = "local"
    inventory_id: str = "repair-unit-private"
    objects: dict[str, bytes] = field(default_factory=dict)
    save_calls: list[str] = field(default_factory=list)
    delete_calls: list[str] = field(default_factory=list)

    async def save(self, *, content, content_hash, extension, content_type, variant):
        del content_type
        key = f"private/{content_hash}/{variant}.{extension}"
        self.save_calls.append(key)
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
        self.delete_calls.append(storage_key)
        self.objects.pop(storage_key, None)

    async def verify_writable(self):
        return None

    async def presign(self, storage_key, *, expires_seconds, download_name=None):
        del storage_key, expires_seconds, download_name
        return None


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
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'repair_diagnostic.db'}"
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session

    await engine.dispose()


def _payload(*, name: str = "Анна", phone: str = "+375291112233"):
    return RepairDiagnosticLeadPayload.model_validate(
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
                "name": name,
                "phone": phone,
                "address": "Витебск, центр",
            },
        }
    )


def _uploads(content: bytes = b"nameplate-content"):
    return {
        "nameplate": [
            RepairDiagnosticIncomingFile(
                filename="nameplate.jpg",
                content_type="image/jpeg",
                content=content,
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


@pytest.mark.asyncio
async def test_repair_diagnostic_creates_private_manager_attachments_and_replays(
    sqlite_repair_diagnostic_session,
    tenant_scope,
):
    storage = FakePrivateStorage()
    payload = _payload()
    uploads = _uploads()

    response, nameplate_files, replayed = await RepairDiagnosticIntakeService.create_lead(
        sqlite_repair_diagnostic_session,
        payload=payload,
        uploads=uploads,
        tenant_scope=tenant_scope,
        idempotency_key="repair-request-unit-0001",
        storage=storage,
    )
    replay_response, _, replayed_again = await RepairDiagnosticIntakeService.create_lead(
        sqlite_repair_diagnostic_session,
        payload=payload,
        uploads=uploads,
        tenant_scope=tenant_scope,
        idempotency_key="repair-request-unit-0001",
        storage=storage,
    )

    assert response.status == "new_lead"
    assert response.ai_pre_diagnosis_status == "pending"
    assert len(nameplate_files) == 1
    assert replayed is False
    assert replayed_again is True
    assert replay_response == response
    assert len(storage.save_calls) == 2
    assert all("public-repair-1-1-" in key for key in storage.save_calls)
    assert storage.delete_calls == []

    order = await sqlite_repair_diagnostic_session.get(Order, response.order_id)
    assert order is not None
    assert order.status == OrderStatus.NEW_LEAD
    assert order.lead_source == LeadSource.SITE
    assert order.tenant_id == tenant_scope.tenant_id
    assert order.storefront_id == tenant_scope.storefront_id
    assert order.workflow_type == "repair"
    assert order.delivery_address == "Витебск, центр"
    assert order.title == "Ремонт кондиционера: Не охлаждает / слабо охлаждает"

    repair_meta = order.technical_meta["repair"]
    photo_ref = repair_meta["photos"]["nameplate"][0]
    assert repair_meta["scenario"] == "repair"
    assert repair_meta["symptom_details"]["outdoor_unit_starts"] == "unknown"
    assert repair_meta["client_checks"] == ["filters_cleaned", "power_restarted"]
    assert photo_ref["content_hash"] == hashlib.sha256(
        b"nameplate-content"
    ).hexdigest()
    assert set(photo_ref) == {
        "attachment_id",
        "filename",
        "content_type",
        "content_hash",
        "size_bytes",
        "uploaded_at",
    }
    assert repair_meta["ai_pre_diagnosis_status"] == "pending"
    assert repair_meta["preliminary_fault_type"] == "refrigerant_leak"
    assert "Фото шильдика" not in repair_meta["missing_data"]

    attachments = list(
        (
            await sqlite_repair_diagnostic_session.execute(
                select(ServiceAttachment).order_by(ServiceAttachment.id)
            )
        ).scalars()
    )
    links = list(
        (
            await sqlite_repair_diagnostic_session.execute(
                select(OrderAttachmentLink).order_by(OrderAttachmentLink.id)
            )
        ).scalars()
    )
    assert len(attachments) == len(links) == 2
    assert attachments[0].source == "website_repair_diagnostic"
    assert attachments[0].source_meta["intake"] == "repair_diagnostic"
    assert attachments[0].source_meta["photo_category"] == "nameplate"
    assert attachments[0].source_meta["purpose"] == "repair_diagnostic_nameplate"
    assert links[0].category == "nameplate"
    assert links[1].category == "defect"

    manager_view = await ServiceAttachmentService.list_order_attachments(
        sqlite_repair_diagnostic_session,
        order_id=response.order_id,
        tenant_scope=tenant_scope,
    )
    foreign_view = await ServiceAttachmentService.list_order_attachments(
        sqlite_repair_diagnostic_session,
        order_id=response.order_id,
        tenant_scope=TenantScope(tenant_id=999, storefront_id=999),
    )
    assert manager_view is not None
    assert manager_view["total"] == 2
    assert foreign_view is None

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
async def test_existing_binary_reuse_stays_private_and_manager_tenant_scoped(
    sqlite_repair_diagnostic_session,
):
    storage = FakePrivateStorage()
    content = b"shared-private-nameplate"
    first_scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True)
    second_scope = TenantScope(tenant_id=2, storefront_id=2)
    first, _, _ = await RepairDiagnosticIntakeService.create_lead(
        sqlite_repair_diagnostic_session,
        tenant_scope=first_scope,
        payload=_payload(name="First", phone="+375291110001"),
        uploads={"nameplate": _uploads(content)["nameplate"]},
        idempotency_key="repair-binary-reuse-first-0001",
        storage=storage,
    )
    second, _, _ = await RepairDiagnosticIntakeService.create_lead(
        sqlite_repair_diagnostic_session,
        tenant_scope=second_scope,
        payload=_payload(name="Second", phone="+375291110002"),
        uploads={"nameplate": _uploads(content)["nameplate"]},
        idempotency_key="repair-binary-reuse-second-0001",
        storage=storage,
    )

    attachments = list(
        (
            await sqlite_repair_diagnostic_session.execute(
                select(ServiceAttachment).order_by(ServiceAttachment.id)
            )
        ).scalars()
    )
    assert len(storage.save_calls) == 1
    assert len(attachments) == 2
    assert attachments[0].storage_key == attachments[1].storage_key
    assert attachments[0].storage_key in storage.objects
    assert (
        await ServiceAttachmentService.list_order_attachments(
            sqlite_repair_diagnostic_session,
            order_id=first.order_id,
            tenant_scope=first_scope,
        )
    )["total"] == 1
    assert (
        await ServiceAttachmentService.list_order_attachments(
            sqlite_repair_diagnostic_session,
            order_id=first.order_id,
            tenant_scope=second_scope,
        )
        is None
    )
    assert (
        await ServiceAttachmentService.list_order_attachments(
            sqlite_repair_diagnostic_session,
            order_id=second.order_id,
            tenant_scope=second_scope,
        )
    )["total"] == 1


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
        len(item.content) for group in uploads.values() for item in group
    ) == MAX_PAYLOAD_BYTES
    assert first.read_sizes == [MAX_PHOTO_BYTES + 1]

    overflow = SizedFakeUpload(b"c" * (MAX_PAYLOAD_BYTES // 2 + 1))
    with pytest.raises(ValueError, match="18 МБ"):
        await RepairDiagnosticService.collect_uploads(
            {"nameplate": [first], "indoor_unit": [overflow]}
        )


@pytest.mark.parametrize(
    "patch",
    [
        {"unexpected": "field"},
        {"symptom_details": {"leak_place": "wall"}},
        {"symptom_details": {"indoor_fan_works": "maybe"}},
        {"client_checks": ["filters_cleaned", "filters_cleaned"]},
        {"client_checks": ["nothing_checked", "filters_cleaned"]},
    ],
)
def test_repair_payload_rejects_unknown_or_invalid_fields(patch):
    data = _payload().model_dump()
    data.update(patch)
    with pytest.raises(ValidationError):
        RepairDiagnosticLeadPayload.model_validate(data)


def test_repair_payload_rejects_oversized_json_before_decoding(monkeypatch):
    decoder_called = False

    def must_not_decode(_raw):
        nonlocal decoder_called
        decoder_called = True
        raise AssertionError("oversized payload reached JSON decoder")

    monkeypatch.setattr(json, "loads", must_not_decode)
    with pytest.raises(ValueError, match="too large"):
        RepairDiagnosticService.parse_payload("x" * (20 * 1024 * 1024))
    assert decoder_called is False


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
    assert (
        "REPAIR_DIAGNOSTIC_NOTIFY_DELIVERY_FAILED order_id=42 admin_id=202"
        in caplog.text
    )
