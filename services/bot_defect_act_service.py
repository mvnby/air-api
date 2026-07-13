import re
from copy import deepcopy
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select

from models import Order
from schemas import ManagerRepairActAiDraftPayload
from services.bot_repair_nameplate_service import BotRepairNameplateService
from services.defect_act_ai_service import DefectActAIService
from services.order_service import OrderService
from services.repair_defect_template_service import RepairDefectTemplateService


class BotDefectActService:
    """Builds and applies compact defect-act drafts for an active repair order."""

    COMMENT_HISTORY_META_KEY = "bot_diagnostic_comments"
    PRESET_FAULT_TYPES = {
        "compressor_short_circuit",
        "compressor_winding_open",
        "compressor_mechanical_failure",
        "heat_exchanger_multiple_leaks",
    }
    COMMENT_FIELDS = (
        "fault_type",
        "fault_location",
        "operation_status",
        "decision",
        "risks",
        "recommended_actions",
        "inspection_codes",
        "confirmed_facts",
        "hidden_defects_possible",
        "structured_diagnosis",
        "defect_act_blocks",
        "customer_complaint",
        "complaint_official",
        "likely_diagnosis",
        "technical_condition",
        "inspection_work_done",
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
    )

    @staticmethod
    def _clean_text(value: Any, *, max_length: int = 1200) -> str:
        text = str(value or "").strip()
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[:max_length].strip()

    @classmethod
    def _normalize_comment_value(cls, value: Any) -> Any:
        if isinstance(value, bool):
            return value
        if isinstance(value, dict):
            return deepcopy(value)
        if isinstance(value, list):
            items = [cls._clean_text(item, max_length=300) for item in value]
            return [item for item in items if item]
        return cls._clean_text(value)

    @staticmethod
    def _has_comment_value(value: Any) -> bool:
        if isinstance(value, bool):
            return True
        return bool(value)

    @classmethod
    def preview_comment_merge(
        cls,
        current_repair_meta: dict[str, Any],
        draft_meta: dict[str, Any],
    ) -> dict[str, Any]:
        changes: dict[str, dict[str, Any]] = {}
        unchanged: dict[str, Any] = {}
        for field in cls.COMMENT_FIELDS:
            candidate = cls._normalize_comment_value(draft_meta.get(field))
            if not cls._has_comment_value(candidate):
                continue
            existing = cls._normalize_comment_value(current_repair_meta.get(field))
            if existing == candidate:
                unchanged[field] = candidate
                continue
            changes[field] = {
                "existing": existing if cls._has_comment_value(existing) else "",
                "candidate": candidate,
            }
        return {"changes": changes, "unchanged": unchanged}

    @classmethod
    def _comment_payload(
        cls,
        *,
        repair_meta: dict[str, Any],
        comment: str,
    ) -> ManagerRepairActAiDraftPayload:
        return ManagerRepairActAiDraftPayload(
            defect_type="field_diagnostic_note",
            defect_label="Диагностическая заметка с выезда",
            allow_assumptions=False,
            polish_existing=True,
            equipment_name=cls._clean_text(repair_meta.get("equipment_name"), max_length=200),
            equipment_brand=cls._clean_text(repair_meta.get("equipment_brand"), max_length=120),
            equipment_model=cls._clean_text(repair_meta.get("equipment_model"), max_length=200),
            equipment_power=cls._clean_text(repair_meta.get("equipment_power"), max_length=120),
            customer_complaint=cls._clean_text(repair_meta.get("customer_complaint"), max_length=500),
            complaint_official=cls._clean_text(repair_meta.get("complaint_official"), max_length=500),
            likely_diagnosis=cls._clean_text(repair_meta.get("likely_diagnosis"), max_length=500),
            extra_context=comment,
            current_meta=repair_meta,
        )

    @classmethod
    async def build_diagnostic_comment_draft(
        cls,
        session: AsyncSession,
        *,
        order_id: int,
        comment: str,
    ) -> dict[str, Any] | None:
        result = await session.execute(
            select(Order)
            .where(Order.id == order_id)
            .options(selectinload(Order.customer))
            .limit(1)
        )
        order = result.scalars().first()
        if not order or OrderService._normalize_workflow_type(order.workflow_type) != "repair":
            return None

        raw_comment = cls._clean_text(comment, max_length=4000)
        if not raw_comment:
            raise ValueError("Комментарий пустой")

        repair_meta = OrderService._get_repair_meta(order)
        ai_meta = await DefectActAIService.generate_repair_meta(
            cls._comment_payload(repair_meta=repair_meta, comment=raw_comment)
        )
        return {
            "order": BotRepairNameplateService._map_order(order),
            "comment": raw_comment,
            "repair_meta": ai_meta,
            "merge_preview": cls.preview_comment_merge(repair_meta, ai_meta),
        }

    @classmethod
    async def build_diagnostic_preset_draft(
        cls,
        session: AsyncSession,
        *,
        order_id: int,
        fault_type: str,
    ) -> dict[str, Any] | None:
        normalized_fault_type = RepairDefectTemplateService.normalize_fault_type(fault_type)
        if normalized_fault_type not in cls.PRESET_FAULT_TYPES:
            raise ValueError("Неизвестный шаблон диагностики")

        result = await session.execute(
            select(Order)
            .where(Order.id == order_id)
            .options(selectinload(Order.customer))
            .limit(1)
        )
        order = result.scalars().first()
        if not order or OrderService._normalize_workflow_type(order.workflow_type) != "repair":
            return None

        repair_meta = OrderService._get_repair_meta(order)
        template = RepairDefectTemplateService.TEMPLATES[normalized_fault_type]
        render_current_meta = {
            key: value
            for key, value in repair_meta.items()
            if key not in DefectActAIService.FIELD_NOTE_REFRESH_KEYS
        }
        preset_meta = RepairDefectTemplateService.build_meta_from_structured(
            raw={
                "fault_type": normalized_fault_type,
                "repairable": template["repairable"],
                "decision": template.get("decision"),
                "operation_status": template["operation_status"],
                "risks": template["risks"],
                "recommended_actions": template["recommended_actions"],
                "inspection_codes": template.get("inspection_codes", []),
                "hidden_defects_possible": False,
            },
            current_meta=render_current_meta,
        )
        return {
            "order": BotRepairNameplateService._map_order(order),
            "comment": f"Типовой диагноз: {template['label']}",
            "repair_meta": preset_meta,
            "merge_preview": cls.preview_comment_merge(repair_meta, preset_meta),
        }

    @classmethod
    async def apply_diagnostic_comment(
        cls,
        session: AsyncSession,
        order_id: int,
        *,
        repair_meta_draft: dict[str, Any],
        raw_comment: str,
        telegram_user_id: int | None,
        telegram_chat_id: int | None,
        telegram_message_id: int | None,
        can_attach_any: bool = False,
    ) -> dict[str, Any] | None:
        allowed = await BotRepairNameplateService.can_use_order(
            session,
            order_id,
            telegram_user_id=telegram_user_id,
            can_attach_any=can_attach_any,
        )
        if not allowed:
            return None

        result = await session.execute(select(Order).where(Order.id == order_id).limit(1))
        order = result.scalars().first()
        if not order:
            return None

        repair_meta = OrderService._get_repair_meta(order)
        merge = cls.preview_comment_merge(repair_meta, repair_meta_draft)
        for field, values in merge["changes"].items():
            repair_meta[field] = values["candidate"]

        raw_history = repair_meta.get(cls.COMMENT_HISTORY_META_KEY)
        history = list(raw_history) if isinstance(raw_history, list) else []
        history.append(
            {
                "source": "telegram_bot",
                "telegram_user_id": telegram_user_id,
                "telegram_chat_id": telegram_chat_id,
                "telegram_message_id": telegram_message_id,
                "comment": cls._clean_text(raw_comment, max_length=4000),
                "ai_meta": {
                    key: deepcopy(value)
                    for key, value in repair_meta_draft.items()
                    if cls._has_comment_value(value)
                },
                "applied_fields": list(merge["changes"].keys()),
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        repair_meta[cls.COMMENT_HISTORY_META_KEY] = history[-20:]
        OrderService._set_repair_meta(
            order,
            repair_meta,
            default_status=OrderService.REPAIR_DEFAULT_STATUS,
        )
        flag_modified(order, "technical_meta")
        session.add(order)
        await session.commit()
        await session.refresh(order)

        return {
            "id": int(order.id or 0),
            "changes": merge["changes"],
            "unchanged": merge["unchanged"],
        }
