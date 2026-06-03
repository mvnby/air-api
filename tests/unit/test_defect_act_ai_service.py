import json

import pytest

from schemas import ManagerRepairActAiDraftPayload
from services.defect_act_ai_service import DefectActAIService


@pytest.mark.asyncio
async def test_defect_act_ai_polishes_existing_fields_by_default(monkeypatch):
    async def _fake_request_completion(prompt: str) -> str:
        assert '"polish_existing": true' in prompt
        return json.dumps(
            {
                "repair_meta": {
                    "measurement_result": "Измерения показали пробой обмотки компрессора на корпус.",
                    "technical_conclusion": "Компрессор неисправен, дальнейшая эксплуатация оборудования запрещена.",
                }
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
                "technical_conclusion": "",
            },
        )
    )

    assert result["measurement_result"].startswith("Измерения показали")
    assert result["technical_conclusion"].startswith("Компрессор неисправен")


@pytest.mark.asyncio
async def test_defect_act_ai_can_leave_existing_fields_untouched(monkeypatch):
    async def _fake_request_completion(prompt: str) -> str:
        assert '"polish_existing": false' in prompt
        return json.dumps(
            {
                "repair_meta": {
                    "measurement_result": "AI tried to rewrite existing value",
                    "technical_conclusion": "Компрессор неисправен.",
                }
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(DefectActAIService, "_request_completion", staticmethod(_fake_request_completion))

    result = await DefectActAIService.generate_repair_meta(
        ManagerRepairActAiDraftPayload(
            defect_type="compressor_winding_breakdown",
            polish_existing=False,
            current_meta={
                "measurement_result": "замерили токи, пробивает на корпус",
                "technical_conclusion": "",
            },
        )
    )

    assert "measurement_result" not in result
    assert result["technical_conclusion"] == "Компрессор неисправен."


@pytest.mark.asyncio
async def test_defect_act_ai_sanitization_keeps_content_keys_and_drops_workflow_keys(monkeypatch):
    async def _fake_request_completion(prompt: str) -> str:
        assert "diagnostic_result" in prompt
        assert "repair_recommendation" in prompt
        return json.dumps(
            {
                "repair_meta": {
                    "diagnostic_result": "Диагностика выявила недостаток хладагента.",
                    "repair_recommendation": "Проверить контур на утечку и дозаправить.",
                    "repair_possible": "Да",
                    "repair_status": "awaiting_customer_approval",
                    "customer_approval_status": "pending",
                    "customer_approval_note": "Ожидается письменное согласование клиента.",
                    "parts_status": "awaiting",
                    "parts_note": "Датчик температуры требуется заказать.",
                    "repair_completion_note": "Завершение возможно после поставки запчастей.",
                    "refrigerant_type": "R32",
                    "refrigerant_amount": "0,35 кг",
                    "refrigerant_pricing_mode": "по фактической массе",
                    "repair_not_viable": "Нет",
                    "repair_not_viable_reason": "Критических повреждений не выявлено.",
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

    assert result["diagnostic_result"] == "Диагностика выявила недостаток хладагента."
    assert result["repair_recommendation"] == "Проверить контур на утечку и дозаправить."
    assert result["repair_possible"] == "Да"
    assert result["refrigerant_type"] == "R32"
    assert result["refrigerant_amount"] == "0,35 кг"
    assert result["refrigerant_pricing_mode"] == "по фактической массе"
    assert result["repair_not_viable"] == "Нет"
    assert result["repair_not_viable_reason"] == "Критических повреждений не выявлено."
    assert "repair_status" not in result
    assert "customer_approval_status" not in result
    assert "customer_approval_note" not in result
    assert "parts_status" not in result
    assert "parts_note" not in result
    assert "repair_completion_note" not in result
    assert "unknown_key" not in result
