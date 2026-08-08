import json
import re
from typing import Any, Dict

from schemas import ManagerRepairActAiDraftPayload
from services.deepseek_provider_service import (
    DefectActAIProviderError,
    request_deepseek_completion,
)
from services.repair_defect_template_service import RepairDefectTemplateService


class DefectActAIService:
    """Builds structured repair diagnostics through an LLM and local templates."""

    ALLOWED_REPAIR_META_KEYS = {
        "fault_type",
        "fault_location",
        "operation_status",
        "risks",
        "recommended_actions",
        "inspection_codes",
        "confirmed_facts",
        "decision",
        "structured_diagnosis",
        "defect_act_blocks",
        "hidden_defects_possible",
        "customer_complaint",
        "complaint_official",
        "likely_diagnosis",
        "diagnostic_notes",
        "equipment_name",
        "equipment_brand",
        "equipment_model",
        "equipment_models",
        "equipment_power",
        "technical_condition",
        "startup_check_result",
        "compressor_check_result",
        "measurement_result",
        "diagnostic_result",
        "further_use_assessment",
        "operation_restrictions",
        "technical_conclusion",
        "repair_feasibility",
        "recommended_decision",
        "repair_recommendation",
        "repair_possible",
        "refrigerant_type",
        "refrigerant_amount",
        "refrigerant_pricing_mode",
        "repair_not_viable",
        "repair_not_viable_reason",
        "repair_estimate_text",
        "inspection_work_done",
    }
    ALLOWED_STRUCTURED_KEYS = {
        "fault_type",
        "fault_location",
        "repairable",
        "operation_status",
        "risks",
        "recommended_actions",
        "refrigerant",
        "refrigerant_type",
        "refrigerant_amount",
        "hidden_defects_possible",
        "inspection_codes",
        "confirmed_facts",
        "decision",
    }
    STRUCTURED_RESPONSE_KEYS = {
        "fault_type",
        "fault_location",
        "operation_status",
        "risks",
        "recommended_actions",
        "inspection_codes",
        "confirmed_facts",
        "decision",
        "structured_diagnosis",
        "defect_act_blocks",
        "hidden_defects_possible",
    }
    PRIMARY_RESPONSE_KEYS = {
        "likely_diagnosis",
        "diagnostic_notes",
        "diagnostic_result",
        "repair_recommendation",
        "repair_possible",
        "repair_not_viable",
        "repair_not_viable_reason",
        "refrigerant_type",
        "refrigerant_amount",
        "repair_estimate_text",
    }
    FIELD_NOTE_RESPONSE_KEYS = PRIMARY_RESPONSE_KEYS | {
        "inspection_work_done",
        "technical_condition",
        "measurement_result",
        "further_use_assessment",
        "operation_restrictions",
        "technical_conclusion",
        "repair_feasibility",
        "recommended_decision",
    }

    FIELD_NOTE_REFRESH_KEYS = {
        "diagnostic_result",
        "repair_recommendation",
        "technical_conclusion",
        "measurement_result",
        "diagnostic_notes",
    }

    @staticmethod
    def _clean_text(value: Any, *, max_length: int = 1200) -> str:
        text = str(value or "").strip()
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[:max_length].strip()

    @staticmethod
    def _clean_meta(raw_meta: Any) -> Dict[str, Any]:
        if not isinstance(raw_meta, dict):
            return {}
        cleaned: Dict[str, Any] = {}
        for key, value in raw_meta.items():
            if key not in DefectActAIService.ALLOWED_REPAIR_META_KEYS:
                continue
            if isinstance(value, dict):
                nested = {
                    str(nested_key): nested_value
                    for nested_key, nested_value in value.items()
                    if isinstance(nested_value, (str, int, float, bool, list, dict)) or nested_value is None
                }
                if nested:
                    cleaned[key] = nested
                continue
            if isinstance(value, list):
                items = [
                    DefectActAIService._clean_text(item, max_length=160)
                    for item in value
                    if DefectActAIService._clean_text(item, max_length=160)
                ]
                if items:
                    cleaned[key] = items
                continue
            if isinstance(value, bool):
                cleaned[key] = value
                continue
            text = DefectActAIService._clean_text(value)
            if text:
                cleaned[key] = text
        return cleaned

    @staticmethod
    def _clean_structured(raw: Any, payload: ManagerRepairActAiDraftPayload) -> Dict[str, Any]:
        if not isinstance(raw, dict):
            raw = {}
        nested = raw.get("structured_diagnosis")
        if isinstance(nested, dict):
            raw = {**raw, **nested}
        cleaned: Dict[str, Any] = {}
        for key in DefectActAIService.ALLOWED_STRUCTURED_KEYS:
            value = raw.get(key)
            if isinstance(value, list):
                items = [
                    DefectActAIService._clean_text(item, max_length=120)
                    for item in value
                    if DefectActAIService._clean_text(item, max_length=120)
                ]
                if key == "inspection_codes":
                    items = [item for item in items if item in RepairDefectTemplateService.INSPECTION_TEXTS]
                if key == "confirmed_facts":
                    items = items[:3]
                cleaned[key] = items
            elif isinstance(value, bool):
                cleaned[key] = value
            elif value is not None:
                text = DefectActAIService._clean_text(value, max_length=200)
                if text:
                    cleaned[key] = text
        if not cleaned.get("fault_type"):
            cleaned["fault_type"] = payload.defect_type
        return cleaned

    @staticmethod
    def build_prompt(payload: ManagerRepairActAiDraftPayload) -> str:
        current_meta = DefectActAIService._clean_meta(payload.current_meta or {})
        fault_types = ", ".join(sorted(RepairDefectTemplateService.TEMPLATES.keys()))
        inspection_codes = ", ".join(sorted(RepairDefectTemplateService.INSPECTION_TEXTS.keys()))
        inputs = {
            "defect_type": payload.defect_type,
            "defect_label": payload.defect_label,
            "allow_assumptions": payload.allow_assumptions,
            "polish_existing": payload.polish_existing,
            "equipment_name": payload.equipment_name,
            "equipment_brand": payload.equipment_brand,
            "equipment_model": payload.equipment_model,
            "equipment_power": payload.equipment_power,
            "customer_complaint": payload.customer_complaint,
            "complaint_official": payload.complaint_official,
            "likely_diagnosis": payload.likely_diagnosis,
            "diagnostic_notes": payload.diagnostic_notes,
            "refrigerant_type": payload.refrigerant_type,
            "refrigerant_amount": payload.refrigerant_amount,
            "extra_context": payload.extra_context,
            "current_meta": current_meta,
        }
        strict_rules = (
            "- Не выдумывай серийный номер, инвентарный номер, дату ввода, точные давления, токи, сопротивления, "
            "температуры и ошибки, если их нет во входных данных.\n"
            "- Не утверждай, что выполнены конкретные измерения сопротивления, давления, токов, температуры или "
            "поиск утечки, если они не указаны прямо и не следуют неизбежно из подтвержденного диагноза "
            "по правилам ниже.\n"
            "- Если нужны дополнительные проверки, формулируй это как рекомендацию или необходимость проверки, "
            "а не как уже выполненное действие.\n"
            "- Для неизвестных измерений используй обобщенные формулировки: визуальный осмотр, проверка запуска, "
            "косвенные признаки, требуется инструментальная проверка.\n"
        )
        assumptions_rules = (
            "- Разрешено выбрать ближайший типовой сценарий списания и его стандартный набор inspection_codes.\n"
            "- Даже в этом режиме не придумывай конкретные симптомы, измерения, даты, номера и выполненные операции.\n"
            "- confirmed_facts оставляй пустым, если факты не названы прямо.\n"
        )
        mode_rules = assumptions_rules if payload.allow_assumptions else strict_rules
        existing_rules = (
            "- Используй current_meta как контекст: уточняй fault_type, risks и recommended_actions по уже заполненным данным.\n"
            "- Не возвращай готовые текстовые поля дефектного акта и не переписывай ручные override-поля.\n"
            "- Строго сохраняй фактический смысл. Не добавляй новые факты, работы, числовые измерения, даты, "
            "серийные или инвентарные номера, которых нет во входных данных.\n"
        ) if payload.polish_existing else (
            "- Если в current_meta уже есть осмысленное значение, учитывай его как контекст, но не возвращай замену этого поля.\n"
            "- Возвращай только структурированные выводы по диагностике и не трогай заполненные ручные поля.\n"
        )

        return (
            "Ты инженер по ремонту систем кондиционирования. Нужно определить структурированные выводы "
            "по диагностике. Ты работаешь как классификатор, а не сочиняешь готовый дефектный акт.\n\n"
            "Документ и смета будут собраны отдельными шаблонами. Не дублируй одну мысль разными словами "
            "и не возвращай длинные документные формулировки.\n\n"
            "Правила:\n"
            "- Верни только JSON-объект без markdown.\n"
            f"{mode_rules}"
            f"{existing_rules}"
            "- confirmed_facts: не более трех коротких фактов, только прямо указанных во входных данных. "
            "Сохраняй числовые значения без изменения; не добавляй выводы от себя.\n"
            "- inspection_codes: только проверки, названные прямо или неизбежно следующие из подтвержденного диагноза.\n"
            "- КЗ, короткое замыкание, межвитковое замыкание или пробой обмоток -> compressor_short_circuit.\n"
            "- Бесконечное сопротивление, нет цепи или обрыв обмотки -> compressor_winding_open.\n"
            "- Компрессор заклинил, хрустит, гремит, не создает перепад давления или вызывает срабатывание автомата "
            "без подтвержденного КЗ/обрыва -> compressor_mechanical_failure.\n"
            "- Много мелких свищей, повторная утечка после пайки, точечная/язвенная коррозия или перфорация теплообменника -> heat_exchanger_multiple_leaks.\n"
            "- Если подтип не подтвержден, выбирай общий compressor_failure или heat_exchanger_damage.\n"
            "- Для compressor_short_circuit и compressor_winding_open допустим winding_resistance_test как проверка, неизбежно следующая из диагноза.\n"
            "- Для heat_exchanger_multiple_leaks допустимы pressure_test и leak_test, если описаны множественные места утечки или повторное вскрытие течи.\n"
            "- Итог должен быть пригоден для выбора локального шаблона и не должен обещать невозможное без диагностики.\n\n"
            "Разрешенные fault_type:\n"
            f"{fault_types}\n\n"
            "Разрешенные inspection_codes:\n"
            f"{inspection_codes}\n\n"
            "Верни JSON в такой структуре:\n"
            "{\n"
            '  "fault_type": "compressor_short_circuit",\n'
            '  "fault_location": "compressor",\n'
            '  "repairable": false,\n'
            '  "decision": "write_off",\n'
            '  "operation_status": "not_allowed",\n'
            '  "risks": ["electrical_damage"],\n'
            '  "recommended_actions": ["decommission_equipment"],\n'
            '  "inspection_codes": ["visual_inspection", "functional_test", "winding_resistance_test"],\n'
            '  "confirmed_facts": ["сопротивление между выводами близко к нулю"],\n'
            '  "refrigerant": null,\n'
            '  "refrigerant_amount": null,\n'
            '  "hidden_defects_possible": false\n'
            "}\n\n"
            "Если данных недостаточно, используй fault_type=unknown_fault и operation_status=unknown.\n\n"
            "Входные данные:\n"
            f"{json.dumps(inputs, ensure_ascii=False, indent=2)}"
        )

    @staticmethod
    def _extract_json_object(content: str) -> Dict[str, Any]:
        text = str(content or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text).strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if not match:
                raise ValueError("AI response does not contain JSON")
            parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            raise ValueError("AI response JSON must be an object")
        nested = parsed.get("repair_meta")
        if isinstance(nested, dict):
            parsed = nested
        return parsed

    @staticmethod
    async def _request_completion(prompt: str) -> str:
        return await request_deepseek_completion(
            prompt=prompt,
            system_prompt=(
                "Ты строгий классификатор результатов диагностики "
                "климатического оборудования."
            ),
            temperature=0.05,
        )

    @staticmethod
    async def generate_repair_meta(payload: ManagerRepairActAiDraftPayload) -> Dict[str, Any]:
        prompt = DefectActAIService.build_prompt(payload)
        content = await DefectActAIService._request_completion(prompt)
        try:
            parsed = DefectActAIService._extract_json_object(content)
        except (ValueError, json.JSONDecodeError) as exc:
            raise DefectActAIProviderError(
                "DeepSeek response does not contain valid classification JSON",
                status=200,
                retryable=True,
                code="invalid_response",
            ) from exc
        structured = DefectActAIService._clean_structured(parsed, payload)
        current_meta = DefectActAIService._clean_meta(payload.current_meta or {})
        render_current_meta = current_meta
        is_field_note = payload.defect_type == "field_diagnostic_note"
        if is_field_note:
            render_current_meta = {
                key: value
                for key, value in current_meta.items()
                if key not in DefectActAIService.FIELD_NOTE_REFRESH_KEYS
            }
        meta = RepairDefectTemplateService.build_meta_from_structured(
            raw=structured,
            current_meta=render_current_meta,
            fallback_fault_type=payload.defect_type,
            diagnostic_notes=payload.diagnostic_notes or payload.extra_context,
        )
        if is_field_note:
            response_keys = (
                DefectActAIService.STRUCTURED_RESPONSE_KEYS
                | DefectActAIService.FIELD_NOTE_RESPONSE_KEYS
            )
            return {
                key: value
                for key, value in meta.items()
                if key in response_keys
            }

        return {
            key: value
            for key, value in meta.items()
            if key in DefectActAIService.STRUCTURED_RESPONSE_KEYS
            or (key in DefectActAIService.PRIMARY_RESPONSE_KEYS and not current_meta.get(key))
        }
