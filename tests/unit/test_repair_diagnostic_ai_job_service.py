import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from models import IntegrationOutboxEvent, Order, OrderStatus
from services.defect_act_ai_service import DefectActAIService
from services.bot_repair_nameplate_service import BotRepairNameplateService
from services.order_service import OrderService
from services.repair_diagnostic_ai_job_service import (
    RepairDiagnosticAiJobService,
)
from services.repair_diagnostic_ai_service import (
    RepairDiagnosticAiLeaseLost,
    RepairDiagnosticAiRetryableError,
    RepairDiagnosticAiService,
)
from services.tenant_scope_service import TenantScope


@pytest.fixture
async def repair_ai_factory(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'repair-ai.db'}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    yield factory
    await engine.dispose()


async def _seed_job(
    factory,
    *,
    max_attempts: int = 8,
) -> tuple[int, str]:
    async with factory() as session:
        order = Order(
            tenant_id=1,
            storefront_id=1,
            title="Repair AI test",
            status=OrderStatus.NEW_LEAD,
            workflow_type="repair",
            technical_meta={
                "repair": {
                    "repair_status": "new",
                    "scenario": "repair",
                    "symptom": "not_cooling",
                    "problem_timing": None,
                    "symptom_details": {},
                    "client_checks": [],
                    "client_comment": "",
                    "contact": {
                        "name": "Test",
                        "phone": "+375291112233",
                        "address": None,
                    },
                    "photos": {},
                    "customer_complaint": "Does not cool",
                    "complaint_official": "Does not cool",
                    "likely_diagnosis": "Needs inspection",
                    "ai_pre_diagnosis_status": "pending",
                }
            },
        )
        session.add(order)
        await session.flush()
        event = await RepairDiagnosticAiJobService.enqueue(
            session,
            order_id=int(order.id or 0),
            tenant_scope=TenantScope(
                tenant_id=1,
                storefront_id=1,
                is_system=True,
            ),
            key_hash="b" * 64,
        )
        event.max_attempts = max_attempts
        session.add(event)
        await session.commit()
        return int(order.id or 0), event.event_id


async def _load(factory, order_id: int, event_id: str):
    async with factory() as session:
        return (
            await session.get(Order, order_id),
            await session.get(IntegrationOutboxEvent, event_id),
        )


@pytest.mark.asyncio
async def test_provider_timeout_propagates_to_durable_retry(
    repair_ai_factory,
    monkeypatch,
):
    order_id, event_id = await _seed_job(repair_ai_factory)
    monkeypatch.setattr(
        "services.repair_diagnostic_ai_service.async_session_maker",
        repair_ai_factory,
    )

    async def timeout(_payload):
        raise httpx.ReadTimeout("provider timeout")

    monkeypatch.setattr(DefectActAIService, "generate_repair_meta", timeout)

    processed = await RepairDiagnosticAiJobService.process_batch(
        worker_id="timeout-worker",
        limit=1,
        session_factory=repair_ai_factory,
    )

    order, event = await _load(repair_ai_factory, order_id, event_id)
    assert processed == 1
    assert event.status == "pending"
    assert event.attempts == 1
    assert event.last_error_code == "repair_ai_provider_timeout"
    assert event.available_at > event.updated_at
    assert OrderService._get_repair_meta(order)["ai_pre_diagnosis_status"] == "pending"


async def _attach_nameplate_reference(factory, order_id: int) -> None:
    async with factory() as session:
        order = await session.get(Order, order_id)
        repair_meta = OrderService._get_repair_meta(order)
        repair_meta["photos"] = {
            "nameplate": [
                {
                    "storage_path": "public-repair-write/1/1/test/nameplate.jpg",
                    "filename": "nameplate.jpg",
                    "content_type": "image/jpeg",
                    "content_hash": "c" * 64,
                }
            ]
        }
        OrderService._set_repair_meta(
            order,
            repair_meta,
            default_status=OrderService.REPAIR_DEFAULT_STATUS,
        )
        session.add(order)
        await session.commit()


@pytest.mark.asyncio
async def test_r2_read_failure_propagates_to_durable_retry(
    repair_ai_factory,
    monkeypatch,
):
    order_id, event_id = await _seed_job(repair_ai_factory)
    await _attach_nameplate_reference(repair_ai_factory, order_id)
    monkeypatch.setattr(
        "services.repair_diagnostic_ai_service.async_session_maker",
        repair_ai_factory,
    )

    class BrokenStorage:
        async def read_media(self, _path):
            raise OSError("R2 unavailable")

    monkeypatch.setattr(
        "services.repair_diagnostic_ai_service.get_general_media_storage",
        lambda: BrokenStorage(),
    )
    await RepairDiagnosticAiJobService.process_batch(
        worker_id="storage-worker",
        limit=1,
        session_factory=repair_ai_factory,
    )

    order, event = await _load(repair_ai_factory, order_id, event_id)
    assert event.status == "pending"
    assert event.last_error_code == "repair_ai_storage_read_unavailable"
    assert OrderService._get_repair_meta(order)["ai_pre_diagnosis_status"] == "pending"


@pytest.mark.asyncio
async def test_ocr_timeout_propagates_to_durable_retry(
    repair_ai_factory,
    monkeypatch,
):
    order_id, event_id = await _seed_job(repair_ai_factory)
    await _attach_nameplate_reference(repair_ai_factory, order_id)
    monkeypatch.setattr(
        "services.repair_diagnostic_ai_service.async_session_maker",
        repair_ai_factory,
    )

    class ReadableStorage:
        async def read_media(self, _path):
            return b"nameplate"

    async def timeout(**_kwargs):
        raise TimeoutError("OCR timeout")

    monkeypatch.setattr(
        "services.repair_diagnostic_ai_service.get_general_media_storage",
        lambda: ReadableStorage(),
    )
    monkeypatch.setattr(BotRepairNameplateService, "recognize_bytes", timeout)
    await RepairDiagnosticAiJobService.process_batch(
        worker_id="ocr-worker",
        limit=1,
        session_factory=repair_ai_factory,
    )

    order, event = await _load(repair_ai_factory, order_id, event_id)
    assert event.status == "pending"
    assert event.last_error_code == "repair_ai_ocr_timeout"
    assert OrderService._get_repair_meta(order)["ai_pre_diagnosis_status"] == "pending"


@pytest.mark.asyncio
async def test_terminal_provider_configuration_is_published_as_skipped(
    repair_ai_factory,
    monkeypatch,
):
    order_id, event_id = await _seed_job(repair_ai_factory)
    monkeypatch.setattr(
        "services.repair_diagnostic_ai_service.async_session_maker",
        repair_ai_factory,
    )

    async def not_configured(_payload):
        raise ValueError("DEEPSEEK_TOKEN is not configured")

    monkeypatch.setattr(
        DefectActAIService,
        "generate_repair_meta",
        not_configured,
    )

    await RepairDiagnosticAiJobService.process_batch(
        worker_id="config-worker",
        limit=1,
        session_factory=repair_ai_factory,
    )

    order, event = await _load(repair_ai_factory, order_id, event_id)
    repair_meta = OrderService._get_repair_meta(order)
    assert event.status == "published"
    assert repair_meta["ai_pre_diagnosis_status"] == "skipped"
    assert repair_meta["ai_pre_diagnosis_error_code"] == (
        "repair_ai_provider_not_configured"
    )


@pytest.mark.asyncio
async def test_retry_exhaustion_atomically_marks_event_and_order_terminal(
    repair_ai_factory,
):
    order_id, event_id = await _seed_job(repair_ai_factory, max_attempts=2)
    async with repair_ai_factory() as session:
        event = await session.get(IntegrationOutboxEvent, event_id)
        event.attempts = 1
        session.add(event)
        await session.commit()

    async def unavailable(**_kwargs):
        raise RepairDiagnosticAiRetryableError(
            "repair_ai_provider_unavailable",
            "provider unavailable",
        )

    await RepairDiagnosticAiJobService.process_batch(
        worker_id="terminal-worker",
        limit=1,
        session_factory=repair_ai_factory,
        runner=unavailable,
    )

    order, event = await _load(repair_ai_factory, order_id, event_id)
    repair_meta = OrderService._get_repair_meta(order)
    assert event.status == "dead"
    assert event.attempts == 2
    assert event.last_error_code == "repair_ai_provider_unavailable"
    assert repair_meta["ai_pre_diagnosis_status"] == "failed"
    assert repair_meta["ai_pre_diagnosis_error_code"] == (
        "repair_ai_provider_unavailable"
    )


@pytest.mark.asyncio
async def test_final_attempt_process_crash_is_recovered_as_terminal_failure(
    repair_ai_factory,
):
    order_id, event_id = await _seed_job(repair_ai_factory, max_attempts=2)
    async with repair_ai_factory() as session:
        event = await session.get(IntegrationOutboxEvent, event_id)
        event.status = "processing"
        event.attempts = 2
        event.worker_id = "crashed-worker"
        event.lease_token = "expired-token"
        event.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.add(event)
        await session.commit()

    runner_calls = 0

    async def must_not_run(**_kwargs):
        nonlocal runner_calls
        runner_calls += 1

    processed = await RepairDiagnosticAiJobService.process_batch(
        worker_id="recovery-worker",
        limit=1,
        session_factory=repair_ai_factory,
        runner=must_not_run,
    )

    order, event = await _load(repair_ai_factory, order_id, event_id)
    assert processed == 1
    assert runner_calls == 0
    assert event.status == "dead"
    assert event.last_error_code == "repair_ai_lease_expired_after_exhaustion"
    assert OrderService._get_repair_meta(order)["ai_pre_diagnosis_status"] == "failed"


@pytest.mark.asyncio
async def test_stale_lease_token_cannot_write_order_or_finish_reclaimed_event(
    repair_ai_factory,
    monkeypatch,
):
    order_id, event_id = await _seed_job(repair_ai_factory)
    now = datetime.now(timezone.utc)
    async with repair_ai_factory() as session:
        async with session.begin():
            stale_claim = await RepairDiagnosticAiJobService._claim_next(
                session,
                worker_id="stale-worker",
                now=now,
            )
    assert stale_claim is not None
    async with repair_ai_factory() as session:
        event = await session.get(IntegrationOutboxEvent, event_id)
        event.lease_expires_at = now - timedelta(seconds=1)
        session.add(event)
        await session.commit()
    async with repair_ai_factory() as session:
        async with session.begin():
            current_claim = await RepairDiagnosticAiJobService._claim_next(
                session,
                worker_id="current-worker",
                now=now,
            )
    assert current_claim is not None
    assert current_claim.lease_token != stale_claim.lease_token

    monkeypatch.setattr(
        "services.repair_diagnostic_ai_service.async_session_maker",
        repair_ai_factory,
    )

    async def successful(_payload):
        return {"diagnostic_result": "safe result"}

    monkeypatch.setattr(
        DefectActAIService,
        "generate_repair_meta",
        successful,
    )
    with pytest.raises(RepairDiagnosticAiLeaseLost):
        await RepairDiagnosticAiService.run(
            order_id=order_id,
            tenant_id=1,
            job_event_id=stale_claim.event_id,
            job_lease_token=stale_claim.lease_token,
        )

    async with repair_ai_factory() as session:
        async with session.begin():
            outcome = await RepairDiagnosticAiJobService._finish(
                session,
                claim=stale_claim,
                error=None,
                now=datetime.now(timezone.utc),
            )
    order, event = await _load(repair_ai_factory, order_id, event_id)
    assert outcome == "lease_lost"
    assert event.lease_token == current_claim.lease_token
    assert OrderService._get_repair_meta(order)["ai_pre_diagnosis_status"] == "pending"


@pytest.mark.asyncio
async def test_heartbeat_prevents_second_replica_from_reclaiming_long_runner(
    repair_ai_factory,
    monkeypatch,
):
    order_id, event_id = await _seed_job(repair_ai_factory)
    monkeypatch.setattr(RepairDiagnosticAiJobService, "LEASE_SECONDS", 0.18)
    started = asyncio.Event()
    contender_calls = 0

    async def long_runner(**_kwargs):
        started.set()
        await asyncio.sleep(0.4)

    async def contender(**_kwargs):
        nonlocal contender_calls
        contender_calls += 1

    primary_task = asyncio.create_task(
        RepairDiagnosticAiJobService.process_batch(
            worker_id="primary-worker",
            limit=1,
            session_factory=repair_ai_factory,
            runner=long_runner,
        )
    )
    await started.wait()
    await asyncio.sleep(0.24)
    contender_processed = await RepairDiagnosticAiJobService.process_batch(
        worker_id="contender-worker",
        limit=1,
        session_factory=repair_ai_factory,
        runner=contender,
    )
    primary_processed = await primary_task

    _order, event = await _load(repair_ai_factory, order_id, event_id)
    assert primary_processed == 1
    assert contender_processed == 0
    assert contender_calls == 0
    assert event.status == "published"
