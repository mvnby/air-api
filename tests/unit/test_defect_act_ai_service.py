import json

import httpx
import pytest

from schemas import ManagerRepairActAiDraftPayload
from services.defect_act_ai_service import (
    DefectActAIProviderError,
    DefectActAIService,
)


class _FakeAsyncClient:
    response: httpx.Response

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def build_request(self, method, url, **kwargs):
        return httpx.Request(method, url, **kwargs)

    async def send(self, *_args, **_kwargs):
        return self.response


class _FakeStream(httpx.AsyncByteStream):
    def __init__(self, body: bytes):
        self.body = body

    async def __aiter__(self):
        yield self.body


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (401, "authentication_rejected", False),
        (403, "authentication_rejected", False),
        (400, "request_rejected", False),
        (429, "rate_limited", True),
        (500, "upstream_error", True),
    ],
)
async def test_deepseek_http_errors_have_typed_retry_contract(
    monkeypatch,
    status,
    code,
    retryable,
):
    monkeypatch.setattr(
        "services.deepseek_provider_service.settings.DEEPSEEK_TOKEN",
        "test-token",
    )
    _FakeAsyncClient.response = httpx.Response(
        status,
        headers={"Content-Type": "application/json"},
        stream=_FakeStream(json.dumps({"error": {"message": "provider error"}}).encode()),
        request=httpx.Request("POST", "https://api.invalid/chat"),
    )
    monkeypatch.setattr(
        "services.deepseek_provider_service.httpx.AsyncClient",
        _FakeAsyncClient,
    )

    with pytest.raises(DefectActAIProviderError) as raised:
        await DefectActAIService._request_completion("prompt")

    assert raised.value.status == status
    assert raised.value.code == code
    assert raised.value.retryable is retryable


@pytest.mark.asyncio
async def test_defect_act_ai_returns_structured_template_meta(monkeypatch):
    async def _fake_request_completion(prompt: str) -> str:
        assert '"polish_existing": true' in prompt
        return json.dumps(
            {
                "fault_type": "compressor_failure",
                "repairable": False,
                "operation_status": "not_allowed",
                "risks": ["electrical_damage"],
                "recommended_actions": ["replace_compressor"],
                "hidden_defects_possible": True,
                "technical_conclusion": "AI must not write expert override fields.",
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(DefectActAIService, "_request_completion", staticmethod(_fake_request_completion))

    result = await DefectActAIService.generate_repair_meta(
        ManagerRepairActAiDraftPayload(
            defect_type="compressor_winding_breakdown",
            polish_existing=True,
            current_meta={
                "measurement_result": "замерили токи, пробивает на корпус",
                "technical_conclusion": "ручное заключение инженера",
            },
        )
    )

    assert result["fault_type"] == "compressor_failure"
    assert result["structured_diagnosis"]["repairable"] is False
    assert result["diagnostic_result"].startswith("Выявлены признаки неисправности компрессора")
    assert result["repair_recommendation"].startswith("Рекомендуется оценить целесообразность")
    assert result["repair_possible"] == "Нет"
    assert "measurement_result" not in result
    assert "technical_conclusion" not in result


@pytest.mark.asyncio
async def test_defect_act_ai_leaves_existing_primary_fields_untouched_when_requested(monkeypatch):
    async def _fake_request_completion(prompt: str) -> str:
        assert '"polish_existing": false' in prompt
        return json.dumps(
            {
                "fault_type": "refrigerant_leak",
                "fault_location": "flare_connections",
                "repairable": True,
                "operation_status": "limited",
                "risks": ["compressor_damage"],
                "recommended_actions": ["restore_circuit_tightness", "vacuuming", "full_refrigerant_charge"],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(DefectActAIService, "_request_completion", staticmethod(_fake_request_completion))

    result = await DefectActAIService.generate_repair_meta(
        ManagerRepairActAiDraftPayload(
            defect_type="refrigerant_leak",
            polish_existing=False,
            current_meta={
                "diagnostic_result": "Уже заполненная диагностика инженера.",
                "repair_recommendation": "",
            },
        )
    )

    assert result["fault_type"] == "refrigerant_leak"
    assert result["structured_diagnosis"]["fault_location"] == "flare_connections"
    assert "diagnostic_result" not in result
    assert result["repair_recommendation"].startswith("Рекомендуется восстановить герметичность")


@pytest.mark.asyncio
async def test_defect_act_ai_sanitization_keeps_structured_keys_and_drops_workflow_keys(monkeypatch):
    async def _fake_request_completion(prompt: str) -> str:
        assert "diagnostic_notes" in prompt
        assert "repair_recommendation" not in prompt.split("Верни JSON в такой структуре:", 1)[1]
        return json.dumps(
            {
                "repair_meta": {
                    "fault_type": "refrigerant_leak",
                    "refrigerant": "R32",
                    "refrigerant_amount": "0,35 кг",
                    "repair_status": "awaiting_customer_approval",
                    "customer_approval_status": "pending",
                    "parts_status": "awaiting",
                    "unknown_key": "must be dropped",
                }
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(DefectActAIService, "_request_completion", staticmethod(_fake_request_completion))

    result = await DefectActAIService.generate_repair_meta(
        ManagerRepairActAiDraftPayload(
            defect_type="refrigerant_leak",
            polish_existing=True,
            current_meta={},
        )
    )

    assert result["fault_type"] == "refrigerant_leak"
    assert result["diagnostic_result"].startswith("Выявлены признаки утечки хладагента")
    assert result["repair_recommendation"].startswith("Рекомендуется восстановить герметичность")
    assert result["repair_possible"] == "Да"
    assert result["refrigerant_type"] == "R32"
    assert result["refrigerant_amount"] == "0,35 кг"
    assert "repair_status" not in result
    assert "customer_approval_status" not in result
    assert "parts_status" not in result
    assert "unknown_key" not in result


@pytest.mark.asyncio
async def test_defect_act_ai_classifies_field_note_into_controlled_write_off_template(monkeypatch):
    async def _fake_request_completion(prompt: str) -> str:
        assert "Бесконечное сопротивление" in prompt
        assert "compressor_winding_open" in prompt
        assert "heat_exchanger_multiple_leaks" in prompt
        assert "Ты работаешь как классификатор" in prompt
        return json.dumps(
            {
                "fault_type": "compressor_winding_open",
                "repairable": True,
                "decision": "repair",
                "operation_status": "not_allowed",
                "inspection_codes": [
                    "visual_inspection",
                    "winding_resistance_test",
                    "invented_check",
                ],
                "confirmed_facts": [
                    "напряжение на компрессор поступает",
                    "обмотка не прозванивается",
                    "факт 3",
                    "факт 4",
                ],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(DefectActAIService, "_request_completion", staticmethod(_fake_request_completion))

    result = await DefectActAIService.generate_repair_meta(
        ManagerRepairActAiDraftPayload(
            defect_type="field_diagnostic_note",
            polish_existing=True,
            extra_context="напряжение приходит, сопротивление бесконечное, обмотка не прозванивается",
            current_meta={"diagnostic_result": "Старый предварительный результат"},
        )
    )

    assert result["fault_type"] == "compressor_winding_open"
    assert result["decision"] == "write_off"
    assert result["structured_diagnosis"]["repairable"] is False
    assert result["inspection_codes"] == ["visual_inspection", "winding_resistance_test"]
    assert len(result["confirmed_facts"]) == 3
    assert "Старый предварительный результат" not in result["diagnostic_result"]
    assert "обмотка не прозванивается" in result["diagnostic_result"]
    assert "подлежит выводу из эксплуатации и списанию" in result["technical_conclusion"]
