import json

import pytest

from models import LeadSource, Order, OrderStatus
from services.general_media_storage_service import StoredGeneralMediaObject


class FakeRepairDiagnosticStorage:
    provider_name = "local"

    async def save_media(self, **kwargs):
        variant_type = kwargs["variant_type"]
        extension = kwargs["extension"]
        return StoredGeneralMediaObject(
            url=f"/media/orders/1/repair-diagnostic/{variant_type}/hash.{extension}",
            content_hash="a" * 64,
            storage_provider="local",
            path=f"media/orders/1/repair-diagnostic/{variant_type}/hash.{extension}",
            size_bytes=len(kwargs["content"]),
        )


@pytest.mark.asyncio
async def test_public_repair_diagnostic_creates_structured_repair_order(async_client, db, monkeypatch):
    monkeypatch.setattr(
        "services.repair_diagnostic_service.get_general_media_storage",
        lambda: FakeRepairDiagnosticStorage(),
    )
    payload = {
        "scenario": "repair",
        "symptom": "water_leak",
        "problem_timing": "after_minutes",
        "symptom_details": {
            "leak_timing": "later",
            "recently_cleaned": "no",
            "drainage_exit": "unknown",
            "leak_place": "body",
        },
        "client_checks": ["filters_cleaned", "drainage_checked"],
        "client_comment": "Капает справа после 10 минут работы",
        "contact": {
            "name": "Иван",
            "phone": "+375 (29) 111-22-33",
            "address": "Витебск, Билево",
        },
    }

    response = await async_client.post(
        "/api/v1/leads/repair-diagnostic",
        files=[
            ("payload", (None, json.dumps(payload), "application/json")),
            ("nameplate", ("nameplate.jpg", b"nameplate-content", "image/jpeg")),
            ("indoor_unit", ("indoor.webp", b"indoor-content", "image/webp")),
        ],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "new_lead"
    assert data["ai_pre_diagnosis_status"] == "pending"

    order = await db.get(Order, data["order_id"])
    assert order is not None
    assert order.tenant_id == 1
    assert order.storefront_id == 1
    assert order.status == OrderStatus.NEW_LEAD
    assert order.lead_source == LeadSource.SITE
    assert order.workflow_type == "repair"
    assert order.title == "Ремонт кондиционера: Течет вода из внутреннего блока"
    assert "предварительной диагностикой" in order.comment

    meta = order.technical_meta
    assert meta["service_type"] == "repair"
    repair_meta = meta["repair"]
    assert repair_meta["scenario"] == "repair"
    assert repair_meta["repair_status"] == "new"
    assert repair_meta["symptom"] == "water_leak"
    assert repair_meta["problem_timing"] == "after_minutes"
    assert repair_meta["client_checks"] == ["filters_cleaned", "drainage_checked"]
    assert repair_meta["symptom_details"]["drainage_exit"] == "unknown"
    assert repair_meta["contact"]["address"] == "Витебск, Билево"
    assert repair_meta["ai_pre_diagnosis_status"] == "pending"
    assert repair_meta["photos"]["nameplate"][0]["url"].endswith("/nameplate/hash.jpg")
    assert repair_meta["photos"]["indoor_unit"][0]["content_type"] == "image/webp"
    assert "Фото шильдика" not in repair_meta["missing_data"]
    assert "Фото внутреннего блока целиком" not in repair_meta["missing_data"]
    assert "Фото места протечки" in repair_meta["missing_data"]
