import json

import pytest

from schemas import ManagerRepairActAiDraftPayload
from services.defect_act_ai_service import DefectActAIService


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
