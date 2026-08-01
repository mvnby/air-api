import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from models import LeadSource, Order, OrderStatus
from core.database import get_session
from services.general_media_storage_service import StoredGeneralMediaObject
from services.repair_diagnostic_intake_service import RepairDiagnosticIntakeService


class FakeRepairDiagnosticStorage:
    provider_name = "local"

    def __init__(self):
        self.objects = {}

    async def save_media(self, **kwargs):
        namespace = kwargs["namespace"]
        variant_type = kwargs["variant_type"]
        extension = kwargs["extension"]
        stored = StoredGeneralMediaObject(
            url=f"/media/{namespace}/{variant_type}/hash.{extension}",
            content_hash="a" * 64,
            storage_provider="local",
            path=f"media/{namespace}/{variant_type}/hash.{extension}",
            size_bytes=len(kwargs["content"]),
        )
        self.objects[stored.path] = kwargs["content"]
        return stored

    async def delete_media(self, path):
        self.objects.pop(path, None)

    async def read_media(self, path):
        return self.objects[path]


class CoordinatedRepairStorage(FakeRepairDiagnosticStorage):
    def __init__(self):
        super().__init__()
        self.first_saved = asyncio.Event()
        self.allow_delete = asyncio.Event()
        self.deleted = []

    async def save_media(self, **kwargs):
        stored = await super().save_media(**kwargs)
        if len(self.objects) == 1:
            self.first_saved.set()
        return stored

    async def delete_media(self, path):
        await self.allow_delete.wait()
        self.deleted.append(path)
        await super().delete_media(path)


@pytest.mark.asyncio
async def test_public_repair_diagnostic_creates_structured_repair_order(async_client, db, monkeypatch):
    storage = FakeRepairDiagnosticStorage()
    monkeypatch.setattr(
        "services.repair_diagnostic_intake_service.get_general_media_storage",
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
    assert repair_meta["photos"]["nameplate"][0]["url"].endswith(
        "/nameplate-0/hash.jpg"
    )
    assert repair_meta["photos"]["indoor_unit"][0]["content_type"] == "image/webp"
    assert "Фото шильдика" not in repair_meta["missing_data"]
    assert "Фото внутреннего блока целиком" not in repair_meta["missing_data"]
    assert "Фото места протечки" in repair_meta["missing_data"]


@pytest.mark.asyncio
async def test_same_key_failed_attempt_cleanup_cannot_delete_committed_successor(
    db_engine,
    monkeypatch,
):
    from main import app

    storage = CoordinatedRepairStorage()
    monkeypatch.setattr(
        "services.repair_diagnostic_intake_service.get_general_media_storage",
        lambda: storage,
    )
    original_mutation = RepairDiagnosticIntakeService._create_mutation
    first_may_fail = asyncio.Event()
    mutation_calls = 0

    async def controlled_mutation(*args, **kwargs):
        nonlocal mutation_calls
        mutation_calls += 1
        attempt = mutation_calls
        order = await original_mutation(*args, **kwargs)
        if attempt == 1:
            await first_may_fail.wait()
            raise RuntimeError("forced first-attempt rollback")
        return order

    async def no_notification(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        RepairDiagnosticIntakeService,
        "_create_mutation",
        controlled_mutation,
    )
    monkeypatch.setattr(
        "services.repair_diagnostic_service.RepairDiagnosticService._notify_admins",
        no_notification,
    )
    request_factory = sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def request_session():
        async with request_factory() as session:
            yield session

    prior_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_session] = request_session
    payload = {
        "scenario": "repair",
        "symptom": "not_cooling",
        "client_checks": [],
        "contact": {
            "name": "Concurrent repair",
            "phone": "+375291112244",
        },
    }
    files = [
        ("payload", (None, json.dumps(payload), "application/json")),
        ("nameplate", ("nameplate.jpg", b"same-photo", "image/jpeg")),
    ]
    headers = {"Idempotency-Key": "repair-concurrent-rollback-0001"}
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            failed_task = asyncio.create_task(
                client.post(
                    "/api/v1/leads/repair-diagnostic",
                    files=files,
                    headers=headers,
                )
            )
            await storage.first_saved.wait()
            successor_task = asyncio.create_task(
                client.post(
                    "/api/v1/leads/repair-diagnostic",
                    files=files,
                    headers=headers,
                )
            )
            first_may_fail.set()
            successor_response = await asyncio.wait_for(
                successor_task,
                timeout=10,
            )
            storage.allow_delete.set()
            failed_response = await asyncio.wait_for(failed_task, timeout=10)
    finally:
        storage.allow_delete.set()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(prior_overrides)

    assert failed_response.status_code == 500
    assert successor_response.status_code == 200
    assert len(storage.deleted) == 1
    async with request_factory() as session:
        orders = list((await session.execute(select(Order))).scalars())
    assert len(orders) == 1
    committed_path = orders[0].technical_meta["repair"]["photos"]["nameplate"][0][
        "storage_path"
    ]
    assert committed_path in storage.objects
    assert storage.deleted[0] != committed_path
