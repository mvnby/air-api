from __future__ import annotations

import pytest

from services.bot_repair_nameplate_service import BotRepairNameplateService
from services.customer_requisites_recognition_service import (
    CustomerRequisitesRecognitionService,
)
from services.defect_act_ai_service import DefectActAIService
from services.google_vision_error_policy import OcrProviderError
from services.order_service import OrderService
from services.repair_diagnostic_ai_job_service import RepairDiagnosticAiJobService
from services.repair_diagnostic_attachment_service import (
    RepairDiagnosticAttachmentService,
)
from tests.unit.test_repair_diagnostic_ai_job_service import (
    _attach_nameplate_reference,
    _load,
    _seed_job,
    repair_ai_factory,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "code"),
    [
        (400, "invalid_argument"),
        (401, "credentials_rejected"),
        (403, "credentials_rejected"),
    ],
)
async def test_terminal_ocr_rejection_is_published_after_one_attempt(
    repair_ai_factory,
    monkeypatch,
    status,
    code,
):
    order_id, event_id = await _seed_job(repair_ai_factory)
    await _attach_nameplate_reference(repair_ai_factory, order_id)
    monkeypatch.setattr(
        "services.repair_diagnostic_ai_service.async_session_maker",
        repair_ai_factory,
    )
    calls = 0

    async def readable(_source):
        return b"nameplate"

    async def rejected(**_kwargs):
        nonlocal calls
        calls += 1
        raise OcrProviderError(
            "OCR request rejected",
            retryable=False,
            code=code,
            status=status,
        )

    async def must_not_reach_ai(_payload):
        raise AssertionError("terminal OCR rejection reached the AI provider")

    monkeypatch.setattr(
        RepairDiagnosticAttachmentService,
        "read_source",
        readable,
    )
    monkeypatch.setattr(BotRepairNameplateService, "recognize_bytes", rejected)
    monkeypatch.setattr(
        DefectActAIService,
        "generate_repair_meta",
        must_not_reach_ai,
    )

    processed = await RepairDiagnosticAiJobService.process_batch(
        worker_id=f"terminal-ocr-{status}",
        limit=1,
        session_factory=repair_ai_factory,
    )
    processed_again = await RepairDiagnosticAiJobService.process_batch(
        worker_id=f"terminal-ocr-{status}-again",
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
    assert repair_meta["ai_pre_diagnosis_error_code"] == f"repair_ai_ocr_{code}"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("rpc_error", "expected_code"),
    [
        (
            {"status": "FAILED_PRECONDITION", "code": 400},
            "failed_precondition",
        ),
        ({"code": 9}, "failed_precondition"),
        ({}, "unclassified_response"),
        (
            {"status": "FUTURE_CANONICAL_STATUS", "code": 14},
            "unclassified_response",
        ),
    ],
)
async def test_terminal_rpc_contract_is_published_after_one_attempt(
    repair_ai_factory,
    monkeypatch,
    rpc_error,
    expected_code,
):
    order_id, event_id = await _seed_job(repair_ai_factory)
    await _attach_nameplate_reference(repair_ai_factory, order_id)
    monkeypatch.setattr(
        "services.repair_diagnostic_ai_service.async_session_maker",
        repair_ai_factory,
    )
    calls = 0
    provider_error = CustomerRequisitesRecognitionService._vision_rpc_error(
        rpc_error
    )

    async def readable(_source):
        return b"nameplate"

    async def rejected(**_kwargs):
        nonlocal calls
        calls += 1
        raise provider_error

    async def must_not_reach_ai(_payload):
        raise AssertionError("terminal OCR rejection reached the AI provider")

    monkeypatch.setattr(
        RepairDiagnosticAttachmentService,
        "read_source",
        readable,
    )
    monkeypatch.setattr(BotRepairNameplateService, "recognize_bytes", rejected)
    monkeypatch.setattr(
        DefectActAIService,
        "generate_repair_meta",
        must_not_reach_ai,
    )

    processed = await RepairDiagnosticAiJobService.process_batch(
        worker_id=f"terminal-rpc-{expected_code}",
        limit=1,
        session_factory=repair_ai_factory,
    )
    processed_again = await RepairDiagnosticAiJobService.process_batch(
        worker_id=f"terminal-rpc-{expected_code}-again",
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
        f"repair_ai_ocr_{expected_code}"
    )
