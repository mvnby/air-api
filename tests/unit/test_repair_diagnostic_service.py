from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from models import LeadSource, Order, OrderStatus
from services.bot_service import BotService
from services.general_media_storage_service import StoredGeneralMediaObject
from services.repair_diagnostic_service import (
    RepairDiagnosticIncomingFile,
    RepairDiagnosticLeadPayload,
    RepairDiagnosticService,
)
from services.staff_user_service import StaffUserService


class FakeRepairDiagnosticStorage:
    provider_name = "local"

    async def save_media(self, **kwargs):
        variant_type = kwargs["variant_type"]
        extension = kwargs["extension"]
        return StoredGeneralMediaObject(
            url=f"/media/orders/42/repair-diagnostic/{variant_type}/hash.{extension}",
            content_hash="c" * 64,
            storage_provider="local",
            path=f"media/orders/42/repair-diagnostic/{variant_type}/hash.{extension}",
            size_bytes=len(kwargs["content"]),
        )


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
    monkeypatch.setattr(
        "services.repair_diagnostic_service.get_general_media_storage",
        lambda: FakeRepairDiagnosticStorage(),
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

    response, nameplate_files = await RepairDiagnosticService.create_lead(
        sqlite_repair_diagnostic_session,
        payload=payload,
        uploads=uploads,
        tenant_scope=tenant_scope,
    )

    assert response.status == "new_lead"
    assert response.ai_pre_diagnosis_status == "pending"
    assert len(nameplate_files) == 1

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


@pytest.mark.asyncio
async def test_repair_notification_escapes_contact_fields(monkeypatch, caplog):
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

    async def fake_recipients(_session):
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
        )

    sent_text = sent_messages[0][1]
    assert "Анна &lt;admin&gt;" in sent_text
    assert "Витебск &amp; &lt;центр&gt;" in sent_text
    assert "<admin>" not in sent_text
    assert len(sent_text) <= BotService.MAX_MESSAGE_LENGTH
    assert "REPAIR_DIAGNOSTIC_NOTIFY_DELIVERY_FAILED order_id=42 admin_id=202" in caplog.text
