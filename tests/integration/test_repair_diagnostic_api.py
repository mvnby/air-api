import hashlib
import io
import json
from dataclasses import dataclass, field

import pytest
from PIL import Image
from sqlmodel import select

from models import (
    LeadSource,
    Order,
    OrderAttachmentLink,
    OrderStatus,
    ServiceAttachment,
)
from services.private_attachment_storage_service import StoredPrivateObject
from services.repair_diagnostic_intake_service import RepairDiagnosticIntakeService


def _image_bytes(image_format: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), color="white").save(buffer, format=image_format)
    return buffer.getvalue()


@dataclass
class FakePrivateStorage:
    provider_name: str = "local"
    inventory_id: str = "repair-api-private"
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


@pytest.mark.asyncio
async def test_public_repair_diagnostic_creates_private_structured_order(
    async_client,
    db,
    monkeypatch,
):
    storage = FakePrivateStorage()
    monkeypatch.setattr(
        "services.repair_diagnostic_intake_service.get_private_attachment_storage",
        lambda: storage,
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
    nameplate_content = _image_bytes("JPEG")
    indoor_content = _image_bytes("PNG")

    response = await async_client.post(
        "/api/v1/leads/repair-diagnostic",
        files=[
            ("payload", (None, json.dumps(payload), "application/json")),
            ("nameplate", ("nameplate.jpg", nameplate_content, "image/jpeg")),
            ("indoor_unit", ("indoor.png", indoor_content, "image/png")),
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

    repair_meta = order.technical_meta["repair"]
    assert repair_meta["scenario"] == "repair"
    assert repair_meta["repair_status"] == "new"
    assert repair_meta["symptom"] == "water_leak"
    assert repair_meta["problem_timing"] == "after_minutes"
    assert repair_meta["client_checks"] == ["filters_cleaned", "drainage_checked"]
    assert repair_meta["symptom_details"]["drainage_exit"] == "unknown"
    assert repair_meta["contact"]["address"] == "Витебск, Билево"
    assert repair_meta["ai_pre_diagnosis_status"] == "pending"
    nameplate_ref = repair_meta["photos"]["nameplate"][0]
    assert set(nameplate_ref) == {
        "attachment_id",
        "filename",
        "content_type",
        "content_hash",
        "size_bytes",
        "uploaded_at",
    }
    assert nameplate_ref["content_hash"] == hashlib.sha256(
        nameplate_content
    ).hexdigest()
    assert repair_meta["photos"]["indoor_unit"][0]["content_type"] == "image/png"
    assert "Фото шильдика" not in repair_meta["missing_data"]
    assert "Фото внутреннего блока целиком" not in repair_meta["missing_data"]
    assert "Фото места протечки" in repair_meta["missing_data"]
    assert storage.delete_calls == []

    attachments = list(
        (await db.execute(select(ServiceAttachment).order_by(ServiceAttachment.id))).scalars()
    )
    links = list(
        (await db.execute(select(OrderAttachmentLink).order_by(OrderAttachmentLink.id))).scalars()
    )
    assert len(attachments) == len(links) == 2
    assert attachments[0].source == "website_repair_diagnostic"
    assert attachments[0].storage_key in storage.objects
    assert links[0].category == "nameplate"


@pytest.mark.asyncio
async def test_public_repair_rejects_20_mib_payload_before_mutation(
    async_client,
    monkeypatch,
):
    intake_called = False

    async def must_not_create(*_args, **_kwargs):
        nonlocal intake_called
        intake_called = True
        raise AssertionError("oversized payload reached database mutation")

    monkeypatch.setattr(
        RepairDiagnosticIntakeService,
        "create_lead",
        must_not_create,
    )
    response = await async_client.post(
        "/api/v1/leads/repair-diagnostic",
        headers={"Idempotency-Key": "repair-oversized-payload-0001"},
        files=[
            (
                "payload",
                (None, "x" * (20 * 1024 * 1024), "application/json"),
            )
        ],
    )

    assert response.status_code in {400, 413}
    assert intake_called is False
