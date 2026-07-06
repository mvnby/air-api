from __future__ import annotations

from copy import deepcopy
from typing import Any


class RepairDefectTemplateService:
    """Templates for structured repair diagnostics and defect-act wording."""

    FAULT_ALIASES = {
        "multiple_heat_exchanger_defects": "heat_exchanger_damage",
        "compressor_winding_breakdown": "compressor_failure",
    }

    DEFAULT_ACTIONS = {
        "restore_circuit_tightness": "восстановить герметичность холодильного контура",
        "replace_faulty_flare_connections": "заменить или переподключить неисправные вальцовочные соединения",
        "vacuuming": "выполнить вакуумирование",
        "full_refrigerant_charge": "заправить хладагентом согласно спецификации производителя",
        "clean_drainage": "прочистить дренажную систему",
        "restore_drainage_slope": "восстановить корректный уклон дренажа",
        "replace_control_board": "заменить плату управления",
        "replace_fan_motor": "заменить двигатель вентилятора",
        "replace_compressor": "заменить компрессор",
        "replace_heat_exchanger": "заменить теплообменник",
        "deep_cleaning": "выполнить глубокую очистку оборудования",
        "correct_installation": "устранить нарушения монтажа",
        "additional_diagnostics": "выполнить дополнительную диагностику",
    }

    RISK_TEXTS = {
        "compressor_damage": "повреждение компрессора",
        "water_leak": "протечка конденсата",
        "electrical_damage": "повреждение электрических компонентов",
        "overheating": "перегрев узлов оборудования",
        "repeated_failure": "повторное возникновение неисправности",
        "low_efficiency": "снижение эффективности работы оборудования",
    }

    TEMPLATES: dict[str, dict[str, Any]] = {
        "refrigerant_leak": {
            "label": "Утечка хладагента",
            "diagnosis_text": "Выявлены признаки утечки хладагента. Давление хладагента ниже нормативного значения.",
            "operation_text": "Эксплуатация оборудования допускается только с ограничениями до проведения ремонта.",
            "risk_text": "Дальнейшая эксплуатация при недостатке хладагента может привести к повреждению компрессора.",
            "repair_text": "Рекомендуется восстановить герметичность холодильного контура, устранить место утечки, выполнить вакуумирование и заправку хладагентом согласно спецификации производителя.",
            "estimate_text": "Устранение утечки хладагента с восстановлением герметичности холодильного контура и заправкой хладагентом согласно спецификации производителя.",
            "operation_status": "limited",
            "repairable": True,
            "risks": ["compressor_damage"],
            "recommended_actions": [
                "restore_circuit_tightness",
                "replace_faulty_flare_connections",
                "vacuuming",
                "full_refrigerant_charge",
            ],
        },
        "drainage_failure": {
            "label": "Нарушение отвода конденсата",
            "diagnosis_text": "Выявлено нарушение отвода конденсата из внутреннего блока.",
            "operation_text": "Эксплуатация допускается после устранения причины протечки конденсата.",
            "risk_text": "Дальнейшая эксплуатация может привести к протечке воды и повреждению отделки или оборудования.",
            "repair_text": "Рекомендуется прочистить дренажную систему, проверить уклон и восстановить штатный отвод конденсата.",
            "estimate_text": "Восстановление отвода конденсата с прочисткой дренажной системы и проверкой уклона.",
            "operation_status": "limited",
            "repairable": True,
            "risks": ["water_leak", "repeated_failure"],
            "recommended_actions": ["clean_drainage", "restore_drainage_slope"],
        },
        "control_board_failure": {
            "label": "Неисправность платы управления",
            "diagnosis_text": "Выявлены признаки неисправности платы управления или цепей управления оборудованием.",
            "operation_text": "Эксплуатация оборудования до ремонта не рекомендуется.",
            "risk_text": "Дальнейшая эксплуатация может привести к нестабильной работе и повреждению электрических компонентов.",
            "repair_text": "Рекомендуется выполнить проверку цепей управления и заменить неисправную плату управления.",
            "estimate_text": "Диагностика цепей управления и замена неисправной платы управления.",
            "operation_status": "not_allowed",
            "repairable": True,
            "risks": ["electrical_damage", "repeated_failure"],
            "recommended_actions": ["replace_control_board"],
        },
        "fan_motor_failure": {
            "label": "Неисправность двигателя вентилятора",
            "diagnosis_text": "Выявлены признаки неисправности двигателя вентилятора или узла вентилятора.",
            "operation_text": "Эксплуатация оборудования до устранения неисправности не рекомендуется.",
            "risk_text": "Дальнейшая эксплуатация может привести к перегреву и повторному повреждению узлов оборудования.",
            "repair_text": "Рекомендуется заменить неисправный двигатель вентилятора и проверить работу оборудования под нагрузкой.",
            "estimate_text": "Замена двигателя вентилятора с проверкой работы оборудования.",
            "operation_status": "not_allowed",
            "repairable": True,
            "risks": ["overheating", "repeated_failure"],
            "recommended_actions": ["replace_fan_motor"],
        },
        "compressor_failure": {
            "label": "Неисправность компрессора",
            "diagnosis_text": "Выявлены признаки неисправности компрессора.",
            "operation_text": "Эксплуатация оборудования не допускается до устранения неисправности.",
            "risk_text": "Дальнейшая эксплуатация может привести к повреждению холодильного контура и электрических компонентов.",
            "repair_text": "Рекомендуется оценить целесообразность замены компрессора с учетом стоимости ремонта и состояния оборудования.",
            "estimate_text": "Диагностика холодильного контура и замена компрессора при экономической целесообразности ремонта.",
            "operation_status": "not_allowed",
            "repairable": False,
            "risks": ["electrical_damage", "repeated_failure"],
            "recommended_actions": ["replace_compressor"],
        },
        "heat_exchanger_damage": {
            "label": "Повреждение теплообменника",
            "diagnosis_text": "Выявлены признаки повреждения или сильного износа теплообменника.",
            "operation_text": "Эксплуатация допускается только после оценки герметичности и состояния теплообменника.",
            "risk_text": "Дальнейшая эксплуатация может привести к утечке хладагента и снижению эффективности оборудования.",
            "repair_text": "Рекомендуется оценить возможность замены теплообменника или целесообразность замены оборудования.",
            "estimate_text": "Диагностика теплообменника и замена поврежденного узла при целесообразности ремонта.",
            "operation_status": "limited",
            "repairable": False,
            "risks": ["low_efficiency", "compressor_damage"],
            "recommended_actions": ["replace_heat_exchanger"],
        },
        "contamination": {
            "label": "Загрязнение оборудования",
            "diagnosis_text": "Выявлено загрязнение теплообменников, фильтров или внутренних узлов оборудования.",
            "operation_text": "Эксплуатация возможна после сервисной очистки оборудования.",
            "risk_text": "Дальнейшая эксплуатация загрязненного оборудования снижает эффективность и повышает нагрузку на узлы.",
            "repair_text": "Рекомендуется выполнить глубокую очистку оборудования и повторную проверку рабочих режимов.",
            "estimate_text": "Глубокая очистка оборудования с повторной проверкой рабочих режимов.",
            "operation_status": "limited",
            "repairable": True,
            "risks": ["low_efficiency", "overheating"],
            "recommended_actions": ["deep_cleaning"],
        },
        "poor_installation": {
            "label": "Нарушение монтажа",
            "diagnosis_text": "Выявлены признаки нарушения требований монтажа оборудования.",
            "operation_text": "Эксплуатация допускается только после устранения выявленных нарушений.",
            "risk_text": "Дальнейшая эксплуатация может привести к повторным неисправностям и повреждению оборудования.",
            "repair_text": "Рекомендуется устранить нарушения монтажа и выполнить контрольную проверку работы оборудования.",
            "estimate_text": "Устранение нарушений монтажа с контрольной проверкой работы оборудования.",
            "operation_status": "limited",
            "repairable": True,
            "risks": ["repeated_failure", "compressor_damage"],
            "recommended_actions": ["correct_installation"],
        },
        "unknown_fault": {
            "label": "Неисправность требует уточнения",
            "diagnosis_text": "Неисправность оборудования требует дополнительной инструментальной диагностики.",
            "operation_text": "Эксплуатация до уточнения причины неисправности не рекомендуется.",
            "risk_text": "Без уточнения причины неисправности возможны повторные отказы и повреждение узлов оборудования.",
            "repair_text": "Рекомендуется выполнить дополнительную диагностику и согласовать ремонт после уточнения причины неисправности.",
            "estimate_text": "Дополнительная диагностика оборудования с последующим согласованием ремонта.",
            "operation_status": "unknown",
            "repairable": True,
            "risks": ["repeated_failure"],
            "recommended_actions": ["additional_diagnostics"],
        },
    }

    @classmethod
    def normalize_fault_type(cls, value: Any) -> str:
        raw = str(value or "").strip()
        raw = cls.FAULT_ALIASES.get(raw, raw)
        return raw if raw in cls.TEMPLATES else "unknown_fault"

    @staticmethod
    def _clean_text(value: Any, max_length: int = 1200) -> str:
        return " ".join(str(value or "").replace("\xa0", " ").split())[:max_length].strip()

    @classmethod
    def _list(cls, value: Any, fallback: list[str]) -> list[str]:
        if isinstance(value, list):
            items = [cls._clean_text(item, 120) for item in value]
            return [item for item in items if item]
        if isinstance(value, str) and value.strip():
            return [cls._clean_text(part, 120) for part in value.split(",") if cls._clean_text(part, 120)]
        return list(fallback)

    @staticmethod
    def _bool(value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        text = str(value or "").strip().lower()
        if text in {"true", "1", "yes", "да"}:
            return True
        if text in {"false", "0", "no", "нет"}:
            return False
        return default

    @classmethod
    def build_structured_findings(cls, raw: dict[str, Any] | None, current_meta: dict[str, Any] | None = None) -> dict[str, Any]:
        raw = raw if isinstance(raw, dict) else {}
        current_meta = current_meta if isinstance(current_meta, dict) else {}
        fault_type = cls.normalize_fault_type(raw.get("fault_type") or current_meta.get("fault_type") or current_meta.get("likely_diagnosis"))
        template = cls.TEMPLATES[fault_type]
        return {
            "fault_type": fault_type,
            "fault_location": cls._clean_text(raw.get("fault_location") or current_meta.get("fault_location"), 160),
            "repairable": cls._bool(raw.get("repairable"), bool(template["repairable"])),
            "operation_status": cls._clean_text(raw.get("operation_status") or template["operation_status"], 80),
            "risks": cls._list(raw.get("risks"), template["risks"]),
            "recommended_actions": cls._list(raw.get("recommended_actions"), template["recommended_actions"]),
            "refrigerant": cls._clean_text(
                raw.get("refrigerant") or raw.get("refrigerant_type") or current_meta.get("refrigerant_type"),
                80,
            ),
            "refrigerant_amount": cls._clean_text(
                raw.get("refrigerant_amount") or current_meta.get("refrigerant_amount"),
                80,
            ),
            "hidden_defects_possible": cls._bool(raw.get("hidden_defects_possible"), True),
        }

    @classmethod
    def render_repair_meta(
        cls,
        *,
        structured: dict[str, Any],
        current_meta: dict[str, Any] | None = None,
        diagnostic_notes: Any = None,
    ) -> dict[str, Any]:
        current_meta = current_meta if isinstance(current_meta, dict) else {}
        fault_type = cls.normalize_fault_type(structured.get("fault_type"))
        template = cls.TEMPLATES[fault_type]
        structured = deepcopy(structured)
        structured["fault_type"] = fault_type

        risks_text = cls._risks_text(structured.get("risks") or template["risks"])
        actions_text = cls._actions_text(structured.get("recommended_actions") or template["recommended_actions"])
        diagnosis_text = cls._clean_text(current_meta.get("diagnostic_result") or template["diagnosis_text"])
        repair_text = cls._clean_text(current_meta.get("repair_recommendation") or template["repair_text"])
        if actions_text and actions_text.lower() not in repair_text.lower():
            repair_text = f"{repair_text} Основные работы: {actions_text}."
        notes = cls._clean_text(diagnostic_notes or current_meta.get("diagnostic_notes") or current_meta.get("measurement_result"), 900)

        hidden_tail = ""
        if structured.get("hidden_defects_possible"):
            hidden_tail = (
                " В процессе ремонта могут быть выявлены дополнительные неисправности, "
                "не определяемые при первичном обследовании и требующие отдельного согласования."
            )

        blocks = {
            "technical_condition": f"Неисправное. {diagnosis_text}",
            "inspection": " ".join(
                part for part in [
                    "Проверена работоспособность оборудования.",
                    notes,
                    diagnosis_text,
                    "Точный объем дефекта уточняется в ходе ремонтных работ с применением специализированного оборудования."
                    if structured.get("hidden_defects_possible")
                    else "",
                ] if part
            ),
            "operation": " ".join(part for part in [template["operation_text"], template["risk_text"], risks_text] if part),
            "conclusion": f"{repair_text}{hidden_tail}",
        }

        return {
            "fault_type": fault_type,
            "fault_location": structured.get("fault_location") or "",
            "operation_status": structured.get("operation_status") or "",
            "risks": structured.get("risks") or [],
            "recommended_actions": structured.get("recommended_actions") or [],
            "hidden_defects_possible": bool(structured.get("hidden_defects_possible")),
            "structured_diagnosis": structured,
            "defect_act_blocks": blocks,
            "likely_diagnosis": template["label"],
            "diagnostic_result": diagnosis_text,
            "diagnostic_notes": notes,
            "inspection_work_done": blocks["inspection"],
            "technical_condition": blocks["technical_condition"],
            "measurement_result": blocks["inspection"],
            "further_use_assessment": template["operation_text"],
            "operation_restrictions": " ".join(part for part in [template["risk_text"], risks_text] if part),
            "repair_recommendation": repair_text,
            "technical_conclusion": blocks["conclusion"],
            "recommended_decision": repair_text,
            "repair_feasibility": "Ремонт возможен." if structured.get("repairable") else "Ремонт невозможен или экономически нецелесообразен.",
            "repair_possible": "Да" if structured.get("repairable") else "Нет",
            "repair_not_viable": "Нет" if structured.get("repairable") else "Да",
            "repair_not_viable_reason": "" if structured.get("repairable") else "Ремонт требует отдельной оценки экономической целесообразности.",
            "refrigerant_type": structured.get("refrigerant") or "",
            "refrigerant_amount": structured.get("refrigerant_amount") or "",
            "repair_estimate_text": template["estimate_text"],
        }

    @classmethod
    def build_meta_from_structured(
        cls,
        *,
        raw: dict[str, Any] | None,
        current_meta: dict[str, Any] | None = None,
        fallback_fault_type: Any = None,
        diagnostic_notes: Any = None,
    ) -> dict[str, Any]:
        raw = raw if isinstance(raw, dict) else {}
        if fallback_fault_type and not raw.get("fault_type"):
            raw = {**raw, "fault_type": fallback_fault_type}
        structured = cls.build_structured_findings(raw, current_meta)
        return cls.render_repair_meta(
            structured=structured,
            current_meta=current_meta,
            diagnostic_notes=diagnostic_notes,
        )

    @classmethod
    def build_document_fields(cls, repair_meta: dict[str, Any] | None) -> dict[str, Any]:
        repair_meta = repair_meta if isinstance(repair_meta, dict) else {}
        structured = repair_meta.get("structured_diagnosis") if isinstance(repair_meta.get("structured_diagnosis"), dict) else {}
        if not structured and repair_meta.get("fault_type"):
            structured = {"fault_type": repair_meta.get("fault_type")}
        if not structured:
            return {}
        return cls.build_meta_from_structured(
            raw=structured,
            current_meta=repair_meta,
            fallback_fault_type=repair_meta.get("fault_type"),
            diagnostic_notes=repair_meta.get("diagnostic_notes") or repair_meta.get("measurement_result"),
        )

    @classmethod
    def _risks_text(cls, risks: Any) -> str:
        labels = [cls.RISK_TEXTS.get(str(item), str(item)) for item in cls._list(risks, [])]
        if not labels:
            return ""
        return "Основные риски: " + ", ".join(labels) + "."

    @classmethod
    def _actions_text(cls, actions: Any) -> str:
        labels = [cls.DEFAULT_ACTIONS.get(str(item), str(item)) for item in cls._list(actions, [])]
        return ", ".join(labels)
