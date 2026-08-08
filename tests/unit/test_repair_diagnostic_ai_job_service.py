import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from models import (
    IntegrationOutboxEvent,
    Order,
    OrderAttachmentLink,
    OrderStatus,
    ServiceAttachment,
)
from services.defect_act_ai_service import (
    DefectActAIProviderError,
    DefectActAIService,
)
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
from services.repair_diagnostic_attachment_service import (
    RepairDiagnosticAttachmentService,
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
                    "client_comment": "FREE-COMMENT-SECRET",
                    "contact": {
                        "name": "NAME-SECRET",
                        "phone": "+375291112233",
                        "address": "ADDRESS-SECRET",
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


async def _attach_nameplate_reference(
    factory,
    order_id: int,
    *,
    source: str = "website_repair_diagnostic",
    category: str = "nameplate",
    source_meta: dict | None = None,
) -> int:
    async with factory() as session:
        order = await session.get(Order, order_id)
        content = b"nameplate"
        attachment = ServiceAttachment(
            original_filename="nameplate.jpg",
            mime_type="image/jpeg",
            size_bytes=len(content),
            content_hash=hashlib.sha256(content).hexdigest(),
            storage_provider="local",
            storage_key="private/nameplate.jpg",
            source=source,
            source_meta=source_meta
            if source_meta is not None
            else {
                "intake": "repair_diagnostic",
                "photo_category": "nameplate",
                "purpose": "repair_diagnostic_nameplate",
            },
        )
        session.add(attachment)
        await session.flush()
        session.add(
            OrderAttachmentLink(
                order_id=order_id,
                attachment_id=int(attachment.id or 0),
                category=category,
            )
        )
        repair_meta = OrderService._get_repair_meta(order)
        repair_meta["photos"] = {
            "nameplate": [
                {
                    "attachment_id": int(attachment.id or 0),
                    "filename": "nameplate.jpg",
                    "content_type": "image/jpeg",
                    "content_hash": attachment.content_hash,
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
        return int(attachment.id or 0)


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

    async def failed_read(_source):
        raise OSError("R2 unavailable")

    monkeypatch.setattr(
        RepairDiagnosticAttachmentService,
        "read_source",
        failed_read,
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

    async def timeout(**_kwargs):
        raise TimeoutError("OCR timeout")

    async def readable(_source):
        return b"nameplate"

    monkeypatch.setattr(
        RepairDiagnosticAttachmentService,
        "read_source",
        readable,
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
        raise DefectActAIProviderError(
            "DEEPSEEK_TOKEN is not configured",
            status=None,
            retryable=False,
            code="not_configured",
        )

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
@pytest.mark.parametrize(
    "attachment_kwargs",
    [
        {"source": "manager"},
        {"category": "defect"},
        {
            "source_meta": {
                "intake": "repair_diagnostic",
                "photo_category": "nameplate",
                "purpose": "repair_diagnostic_indoor_unit",
            }
        },
    ],
)
async def test_nameplate_resolver_rejects_wrong_source_category_or_purpose(
    repair_ai_factory,
    monkeypatch,
    attachment_kwargs,
):
    order_id, event_id = await _seed_job(repair_ai_factory)
    await _attach_nameplate_reference(
        repair_ai_factory,
        order_id,
        **attachment_kwargs,
    )
    monkeypatch.setattr(
        "services.repair_diagnostic_ai_service.async_session_maker",
        repair_ai_factory,
    )
    provider_calls = 0

    async def must_not_call_provider(_payload):
        nonlocal provider_calls
        provider_calls += 1

    monkeypatch.setattr(
        DefectActAIService,
        "generate_repair_meta",
        must_not_call_provider,
    )

    await RepairDiagnosticAiJobService.process_batch(
        worker_id="invalid-attachment-worker",
        limit=1,
        session_factory=repair_ai_factory,
    )

    order, event = await _load(repair_ai_factory, order_id, event_id)
    repair_meta = OrderService._get_repair_meta(order)
    assert provider_calls == 0
    assert event.status == "published"
    assert repair_meta["ai_pre_diagnosis_status"] == "failed"
    assert repair_meta["ai_pre_diagnosis_error_code"] == (
        "repair_ai_nameplate_reference_invalid"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_authentication_rejection_is_terminal_after_one_attempt(
    repair_ai_factory,
    monkeypatch,
    status,
):
    order_id, event_id = await _seed_job(repair_ai_factory)
    monkeypatch.setattr(
        "services.repair_diagnostic_ai_service.async_session_maker",
        repair_ai_factory,
    )
    calls = 0

    async def rejected(_payload):
        nonlocal calls
        calls += 1
        raise DefectActAIProviderError(
            "credentials rejected",
            status=status,
            retryable=False,
            code="authentication_rejected",
        )

    monkeypatch.setattr(DefectActAIService, "generate_repair_meta", rejected)
    processed = await RepairDiagnosticAiJobService.process_batch(
        worker_id=f"auth-{status}-worker",
        limit=1,
        session_factory=repair_ai_factory,
    )
    processed_again = await RepairDiagnosticAiJobService.process_batch(
        worker_id=f"auth-{status}-worker-2",
        limit=1,
        session_factory=repair_ai_factory,
    )

    order, event = await _load(repair_ai_factory, order_id, event_id)
    repair_meta = OrderService._get_repair_meta(order)
    assert processed == 1
    assert processed_again == 0
    assert calls == 1
    assert event.status == "published"
    assert event.attempts == 1
    assert repair_meta["ai_pre_diagnosis_status"] == "failed"
    assert repair_meta["ai_pre_diagnosis_error_code"] == (
        "repair_ai_provider_authentication_rejected"
    )


@pytest.mark.asyncio
async def test_rate_limit_is_retryable(repair_ai_factory, monkeypatch):
    order_id, event_id = await _seed_job(repair_ai_factory)
    monkeypatch.setattr(
        "services.repair_diagnostic_ai_service.async_session_maker",
        repair_ai_factory,
    )

    async def rate_limited(_payload):
        raise DefectActAIProviderError(
            "rate limited",
            status=429,
            retryable=True,
            code="rate_limited",
        )

    monkeypatch.setattr(DefectActAIService, "generate_repair_meta", rate_limited)
    await RepairDiagnosticAiJobService.process_batch(
        worker_id="rate-limit-worker",
        limit=1,
        session_factory=repair_ai_factory,
    )

    order, event = await _load(repair_ai_factory, order_id, event_id)
    assert event.status == "pending"
    assert event.attempts == 1
    assert event.last_error_code == "repair_ai_provider_rate_limited"
    assert OrderService._get_repair_meta(order)["ai_pre_diagnosis_status"] == "pending"


@pytest.mark.asyncio
async def test_provider_payload_excludes_contact_address_and_free_comment(
    repair_ai_factory,
    monkeypatch,
):
    order_id, event_id = await _seed_job(repair_ai_factory)
    monkeypatch.setattr(
        "services.repair_diagnostic_ai_service.async_session_maker",
        repair_ai_factory,
    )
    captured = []

    async def capture(payload):
        captured.append(payload.model_dump_json())
        return {"diagnostic_result": "safe result"}

    monkeypatch.setattr(DefectActAIService, "generate_repair_meta", capture)
    await RepairDiagnosticAiJobService.process_batch(
        worker_id="pii-fence-worker",
        limit=1,
        session_factory=repair_ai_factory,
    )

    _order, event = await _load(repair_ai_factory, order_id, event_id)
    assert event.status == "published"
    assert len(captured) == 1
    provider_payload = captured[0]
    assert "NAME-SECRET" not in provider_payload
    assert "+375291112233" not in provider_payload
    assert "ADDRESS-SECRET" not in provider_payload
    assert "FREE-COMMENT-SECRET" not in provider_payload


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
