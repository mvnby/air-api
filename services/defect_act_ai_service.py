import json
import re
from typing import Any, Dict

import httpx

from core.config import settings
from schemas import ManagerRepairActAiDraftPayload


class DefectActAIService:
    """Builds repair defect-act field drafts through an LLM."""

    ALLOWED_REPAIR_META_KEYS = {
        "customer_complaint",
        "complaint_official",
        "likely_diagnosis",
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
        "inspection_work_done",
    }

    @staticmethod
    def _clean_text(value: Any, *, max_length: int = 1200) -> str:
        text = str(value or "").strip()
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[:max_length].strip()

    @staticmethod
    def _clean_meta(raw_meta: Any) -> Dict[str, str]:
        if not isinstance(raw_meta, dict):
            return {}
        cleaned: Dict[str, str] = {}
        for key, value in raw_meta.items():
            if key not in DefectActAIService.ALLOWED_REPAIR_META_KEYS:
                continue
            text = DefectActAIService._clean_text(value)
            if text:
                cleaned[key] = text
        return cleaned

    @staticmethod
    def build_prompt(payload: ManagerRepairActAiDraftPayload) -> str:
        current_meta = DefectActAIService._clean_meta(payload.current_meta or {})
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
            "- Если в current_meta уже есть осмысленное значение, можно улучшить его стиль: "
            "исправить терминологию, сделать формулировку официальной, раскрыть мысль до уровня дефектного акта.\n"
            "- При улучшении заполненных полей строго сохраняй фактический смысл. Не добавляй новые факты, работы, "
            "числовые измерения, даты, серийные или инвентарные номера, которых нет во входных данных.\n"
        ) if payload.polish_existing else (
            "- Если в current_meta уже есть осмысленное значение, не переписывай это поле и не возвращай его в ответе.\n"
            "- Заполняй только пустые или явно неполные поля, опираясь на входные данные.\n"
        )

        return (
            "Ты инженер по ремонту систем кондиционирования и составляешь текстовые поля "
            "для дефектного акта на русском языке.\n\n"
            "Нужно заполнить значения для Google Docs-плейсхолдеров дефектного акта. "
            "Пиши официально, по-деловому, без маркетинга и без разговорных формулировок.\n\n"
            "Правила:\n"
            "- Верни только JSON-объект без markdown.\n"
            f"{mode_rules}"
            f"{existing_rules}"
            "- Итог должен быть пригоден для дефектного акта, но не должен обещать невозможное без диагностики.\n\n"
            "Разрешенные ключи JSON:\n"
            + ", ".join(sorted(DefectActAIService.ALLOWED_REPAIR_META_KEYS))
            + "\n\n"
            "Смысл ключей:\n"
            "customer_complaint - простая жалоба клиента; "
            "complaint_official - официальная формулировка жалобы для акта; "
            "likely_diagnosis - вероятная причина; "
            "technical_condition - техническое состояние оборудования; "
            "startup_check_result - результат проверки запуска; "
            "compressor_check_result - проверка компрессора; "
            "measurement_result - результаты диагностики/замеров без выдуманных чисел; "
            "diagnostic_result - канонический результат диагностики; "
            "further_use_assessment - возможность дальнейшей эксплуатации; "
            "operation_restrictions - ограничения эксплуатации; "
            "technical_conclusion - итоговое техническое заключение; "
            "repair_feasibility - целесообразность ремонта; "
            "recommended_decision - рекомендованное решение; "
            "repair_recommendation - каноническая рекомендация по ремонту; "
            "repair_possible - возможен ли ремонт; "
            "refrigerant_type - тип хладагента; "
            "refrigerant_amount - объем хладагента; "
            "refrigerant_pricing_mode - способ расчета хладагента; "
            "repair_not_viable - ремонт невозможен или нецелесообразен; "
            "repair_not_viable_reason - причина невозможности или нецелесообразности ремонта; "
            "inspection_work_done - выполненные диагностические действия.\n\n"
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
    async def generate_repair_meta(payload: ManagerRepairActAiDraftPayload) -> Dict[str, str]:
        prompt = DefectActAIService.build_prompt(payload)
        content = await DefectActAIService._request_completion(prompt)
        parsed = DefectActAIService._extract_json_object(content)
        meta = DefectActAIService._clean_meta(parsed)
        if payload.polish_existing:
            return meta

        existing_meta = DefectActAIService._clean_meta(payload.current_meta or {})
        return {
            key: value
            for key, value in meta.items()
            if not existing_meta.get(key)
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
