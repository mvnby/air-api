import json
import re
from typing import Any, Dict

import httpx

from core.config import settings
from schemas import ManagerRepairActAiDraftPayload
from services.repair_defect_template_service import RepairDefectTemplateService


class DefectActAIService:
    """Builds structured repair diagnostics through an LLM and local templates."""

    ALLOWED_REPAIR_META_KEYS = {
        "fault_type",
        "fault_location",
        "operation_status",
        "risks",
        "recommended_actions",
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
    }
    STRUCTURED_RESPONSE_KEYS = {
        "fault_type",
        "fault_location",
        "operation_status",
        "risks",
        "recommended_actions",
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
                cleaned[key] = [
                    DefectActAIService._clean_text(item, max_length=120)
                    for item in value
                    if DefectActAIService._clean_text(item, max_length=120)
                ]
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
            "поиск утечки, если такие работы и результаты прямо не указаны во входных данных.\n"
            "- Если нужны дополнительные проверки, формулируй это как рекомендацию или необходимость проверки, "
            "а не как уже выполненное действие.\n"
            "- Для неизвестных измерений используй обобщенные формулировки: визуальный осмотр, проверка запуска, "
            "косвенные признаки, требуется инструментальная проверка.\n"
        )
        assumptions_rules = (
            "- Разрешен бюрократический сценарий списания: можно заполнить акт на основании типовой картины дефекта, "
            "даже если фактические замеры и часть деталей не указаны.\n"
            "- Не придумывай серийный или инвентарный номер. Не указывай точные числовые замеры, если их нет.\n"
            "- Можно формулировать осмотр и выводы как типовые: визуальные дефекты, износ, коррозия, следы длительного хранения, "
            "отсутствие целесообразности ремонта, вывод из эксплуатации или списание.\n"
            "- Делай текст цельным и уверенным для дефектного акта, но без лишних технических чисел.\n"
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
            "по диагностике, а не писать готовый дефектный акт.\n\n"
            "Документ и смета будут собраны отдельными шаблонами. Не дублируй одну мысль разными словами "
            "и не возвращай длинные документные формулировки.\n\n"
            "Правила:\n"
            "- Верни только JSON-объект без markdown.\n"
            f"{mode_rules}"
            f"{existing_rules}"
            "- Итог должен быть пригоден для выбора шаблона, но не должен обещать невозможное без диагностики.\n\n"
            "Разрешенные fault_type:\n"
            f"{fault_types}\n\n"
            "Верни JSON в такой структуре:\n"
            "{\n"
            '  "fault_type": "refrigerant_leak",\n'
            '  "fault_location": "flare_connections",\n'
            '  "repairable": true,\n'
            '  "operation_status": "limited",\n'
            '  "risks": ["compressor_damage"],\n'
            '  "recommended_actions": ["restore_circuit_tightness", "vacuuming", "full_refrigerant_charge"],\n'
            '  "refrigerant": "R410A",\n'
            '  "refrigerant_amount": "790 g",\n'
            '  "hidden_defects_possible": true\n'
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
        token = settings.DEEPSEEK_TOKEN.strip()
        if not token:
            raise ValueError("DEEPSEEK_TOKEN is not configured")

        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                settings.DEEPSEEK_API_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.DEEPSEEK_MODEL,
                    "temperature": 0.35,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": "Ты аккуратный технический редактор дефектных актов по климатическому оборудованию.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            if response.status_code == 401:
                raise ValueError("DeepSeek отклонил API ключ. Проверьте DEEPSEEK_TOKEN в .env и перезапустите app-контейнер.")
            if response.status_code == 403:
                raise ValueError("DeepSeek запретил доступ для этого API ключа. Проверьте права ключа и баланс аккаунта.")
            if response.status_code >= 400:
                detail = DefectActAIService._deepseek_error_message(response)
                raise ValueError(f"DeepSeek вернул ошибку {response.status_code}: {detail}")
            data = response.json()

        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("AI response has unexpected format") from exc

    @staticmethod
    async def generate_repair_meta(payload: ManagerRepairActAiDraftPayload) -> Dict[str, Any]:
        prompt = DefectActAIService.build_prompt(payload)
        content = await DefectActAIService._request_completion(prompt)
        parsed = DefectActAIService._extract_json_object(content)
        structured = DefectActAIService._clean_structured(parsed, payload)
        current_meta = DefectActAIService._clean_meta(payload.current_meta or {})
        meta = RepairDefectTemplateService.build_meta_from_structured(
            raw=structured,
            current_meta=current_meta,
            fallback_fault_type=payload.defect_type,
            diagnostic_notes=payload.diagnostic_notes or payload.extra_context,
        )
        response_keys = DefectActAIService.STRUCTURED_RESPONSE_KEYS | DefectActAIService.PRIMARY_RESPONSE_KEYS
        if payload.polish_existing:
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

    @staticmethod
    def _deepseek_error_message(response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return response.text[:300]
        error = data.get("error") if isinstance(data, dict) else None
        if isinstance(error, dict):
            message = str(error.get("message") or "").strip()
            if message:
                return message[:300]
        return str(data)[:300]
