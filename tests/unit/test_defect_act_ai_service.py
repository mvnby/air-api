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
