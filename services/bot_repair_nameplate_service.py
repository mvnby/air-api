import re
from datetime import datetime
from typing import Any, Optional

import httpx
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select

from core.config import settings
from models import Order, OrderInstaller, OrderStatus, OrderWorkStage, StaffUser
from services.bot_order_attachment_service import BotOrderAttachmentService
from services.customer_requisites_recognition_service import CustomerRequisitesRecognitionService
from services.defect_act_ai_service import DefectActAIService
from services.order_service import OrderService
from services.staff_user_service import StaffUserService
from schemas import ManagerRepairActAiDraftPayload


class BotRepairNameplateService:
    """Recognizes AC nameplates and safely applies passport fields to repair orders."""

    REPAIR_STATUS = OrderStatus.EXECUTION
    REPAIR_FIELDS = (
        "equipment_name",
        "equipment_brand",
        "equipment_model",
        "equipment_power",
        "equipment_serial_number",
        "equipment_inventory_number",
        "equipment_commissioning_date",
        "refrigerant_type",
        "refrigerant_amount",
    )
    FIELD_LABELS = {
        "equipment_name": "Оборудование",
        "equipment_brand": "Бренд",
        "equipment_model": "Модель",
        "equipment_power": "Мощность",
        "equipment_serial_number": "Серийный номер",
        "equipment_inventory_number": "Инвентарный номер",
        "equipment_commissioning_date": "Дата ввода",
        "refrigerant_type": "Хладагент",
        "refrigerant_amount": "Количество хладагента",
    }
    HISTORY_META_KEY = "nameplate_recognitions"
    COMMENT_HISTORY_META_KEY = "bot_diagnostic_comments"
    COMMENT_FIELDS = (
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
    )
    COMMENT_FIELD_LABELS = {
        "customer_complaint": "Жалоба клиента",
        "complaint_official": "Жалоба для акта",
        "likely_diagnosis": "Вероятная причина",
        "technical_condition": "Техническое состояние",
        "startup_check_result": "Проверка запуска",
        "compressor_check_result": "Проверка компрессора",
        "measurement_result": "Результаты замеров",
        "diagnostic_result": "Результат диагностики",
        "further_use_assessment": "Дальнейшая эксплуатация",
        "operation_restrictions": "Ограничения эксплуатации",
        "technical_conclusion": "Техническое заключение",
        "repair_feasibility": "Целесообразность ремонта",
        "recommended_decision": "Рекомендованное решение",
        "repair_recommendation": "Рекомендация по ремонту",
        "repair_possible": "Ремонт возможен",
        "refrigerant_type": "Хладагент",
        "refrigerant_amount": "Количество хладагента",
        "refrigerant_pricing_mode": "Расчет хладагента",
        "repair_not_viable": "Ремонт нецелесообразен",
        "repair_not_viable_reason": "Причина нецелесообразности",
        "inspection_work_done": "Выполненные работы",
    }

    @staticmethod
    def _clean_text(value: Any, *, max_length: int = 500) -> Optional[str]:
        text = str(value or "").strip()
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[:max_length].strip() or None

    @classmethod
    def _normalize_refrigerant_type(cls, value: Any) -> Optional[str]:
        text = cls._clean_text(value, max_length=40)
        if not text:
            return None
        text = text.upper().replace(" ", "")
        text = text.replace("R-410A", "R410A").replace("R-32", "R32").replace("R-22", "R22")
        match = re.search(r"\bR\d{2,3}[A-Z]?\b", text)
        return match.group(0) if match else text

    @classmethod
    def _normalize_refrigerant_amount(cls, value: Any) -> Optional[str]:
        text = cls._clean_text(value, max_length=80)
        if not text:
            return None
        text = text.replace("КГ", "кг").replace("KG", "кг").replace("kg", "кг")
        text = re.sub(r"\s*/\s*", "/", text)
        match = re.search(r"(\d+(?:[.,]\d+)?)\s*кг", text, flags=re.IGNORECASE)
        if match:
            return f"{match.group(1).replace('.', ',')} кг"
        return text

    @classmethod
    def _normalize_power(cls, value: Any, raw: dict[str, Any]) -> Optional[str]:
        text = cls._clean_text(value, max_length=120)
        if text:
            return text
        btu = cls._clean_text(raw.get("capacity_btu") or raw.get("cooling_capacity_btu"), max_length=40)
        if btu:
            digits = re.sub(r"\D", "", btu)
            return f"{digits} BTU/h" if digits else btu
        kw = cls._clean_text(raw.get("cooling_capacity_kw") or raw.get("capacity_kw"), max_length=40)
        if kw:
            return kw if "кВт" in kw else f"{kw} кВт"
        return None

    @classmethod
    def _is_repair_execution_order(cls, order: Order | None) -> bool:
        if not order:
            return False
        workflow_type = OrderService._normalize_workflow_type(getattr(order, "workflow_type", None))
        return workflow_type == "repair" and order.status == cls.REPAIR_STATUS

    @staticmethod
    def _map_order(order: Order) -> dict[str, Any]:
        customer = getattr(order, "customer", None)
        return {
            "id": int(order.id or 0),
            "title": order.title,
            "status": order.status.value if hasattr(order.status, "value") else str(order.status),
            "workflow_type": OrderService._normalize_workflow_type(getattr(order, "workflow_type", None)),
            "customer_name": getattr(customer, "name", None) if customer else None,
            "customer_phone": getattr(customer, "phone", None) if customer else None,
            "address": order.delivery_address,
            "updated_at": order.updated_at,
            "created_at": order.created_at,
        }

    @classmethod
    async def _legacy_installer_id(cls, session: AsyncSession, telegram_user_id: int | str | None) -> Optional[int]:
        try:
            normalized_telegram_id = int(telegram_user_id) if telegram_user_id is not None else 0
        except (TypeError, ValueError):
            return None
        if not normalized_telegram_id:
            return None

        result = await session.execute(
            select(StaffUser)
            .where(StaffUser.telegram_id == normalized_telegram_id)
            .where(StaffUser.status == StaffUserService.STATUS_ACTIVE)
            .order_by(StaffUser.id.asc())
            .limit(1)
        )
        staff = result.scalars().first()
        installer_id = getattr(staff, "legacy_installer_id", None)
        return int(installer_id) if installer_id else None

    @classmethod
    async def list_repair_orders(
        cls,
        session: AsyncSession,
        *,
        telegram_user_id: int | str | None,
        can_attach_any: bool = False,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(Order)
            .where(Order.status == cls.REPAIR_STATUS)
            .where(Order.workflow_type == "repair")
            .options(selectinload(Order.customer))
            .order_by(Order.updated_at.desc(), Order.created_at.desc(), Order.id.desc())
            .limit(max(1, min(limit, 10)))
        )

        if not can_attach_any:
            installer_id = await cls._legacy_installer_id(session, telegram_user_id)
            if not installer_id:
                return []
            stage_exists = (
                select(OrderWorkStage.id)
                .where(OrderWorkStage.order_id == Order.id)
                .where(OrderWorkStage.installer_id == installer_id)
                .exists()
            )
            legacy_exists = (
                select(OrderInstaller.order_id)
                .where(OrderInstaller.order_id == Order.id)
                .where(OrderInstaller.installer_id == installer_id)
                .exists()
            )
            stmt = stmt.where(or_(stage_exists, legacy_exists))

        result = await session.execute(stmt)
        return [cls._map_order(order) for order in result.scalars().all()]

    @classmethod
    async def can_use_order(
        cls,
        session: AsyncSession,
        order_id: int,
        *,
        telegram_user_id: int | str | None,
        can_attach_any: bool = False,
    ) -> bool:
        result = await session.execute(select(Order).where(Order.id == order_id).limit(1))
        order = result.scalars().first()
        if not cls._is_repair_execution_order(order):
            return False
        if can_attach_any:
            return True
        return await BotOrderAttachmentService.can_attach_to_order(
            session,
            order_id,
            telegram_user_id=telegram_user_id,
        )

    @classmethod
    def build_extraction_prompt(cls, raw_text: str) -> str:
        return (
            "Ты извлекаешь данные с шильдика кондиционера для дефектного акта ремонта.\n"
            "Верни только JSON-объект без markdown. Не выдумывай данные: если поле не видно, верни null.\n\n"
            "Ключи JSON:\n"
            "equipment_name, equipment_brand, equipment_model, equipment_power, equipment_serial_number, "
            "equipment_inventory_number, equipment_commissioning_date, refrigerant_type, refrigerant_amount, "
            "unit_type, capacity_btu, cooling_capacity_kw, raw_markings, confidence, warnings.\n\n"
            "Правила:\n"
            "- equipment_name: человекочитаемо, например 'Кондиционер, наружный блок' или 'Кондиционер'.\n"
            "- equipment_model: модель блока ровно как на шильдике.\n"
            "- equipment_serial_number: серийный номер/SN/Serial No, только если он явно виден.\n"
            "- equipment_power: полезная холодопроизводительность/мощность, как на шильдике; не путай с потребляемой мощностью.\n"
            "- refrigerant_type: R32, R410A, R22 и т.п.\n"
            "- refrigerant_amount: заводская заправка, например '0,60 кг'.\n"
            "- raw_markings: короткий список важных строк с шильдика.\n"
            "- confidence: число от 0 до 1.\n"
            "- warnings: массив коротких предупреждений.\n\n"
            "OCR-текст:\n"
            f"{raw_text[:12000]}"
        )

    @classmethod
    async def extract_nameplate(cls, raw_text: str) -> dict[str, Any]:
        token = settings.DEEPSEEK_TOKEN.strip()
        if not token:
            raise ValueError("DEEPSEEK_TOKEN is not configured")

        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                settings.DEEPSEEK_API_URL,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={
                    "model": settings.DEEPSEEK_MODEL,
                    "temperature": 0.02,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": "Ты аккуратно извлекаешь паспортные данные HVAC оборудования и возвращаешь строгий JSON.",
                        },
                        {"role": "user", "content": cls.build_extraction_prompt(raw_text)},
                    ],
                },
            )
            if response.status_code >= 400:
                raise ValueError(f"DeepSeek вернул ошибку {response.status_code}: {response.text[:300]}")
            data = response.json()

        try:
            content = str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("AI response has unexpected format") from exc
        return CustomerRequisitesRecognitionService._extract_json_object(content)

    @classmethod
    def normalize_extracted(cls, raw: dict[str, Any], raw_text: str) -> tuple[dict[str, Any], dict[str, Any]]:
        data = {
            "equipment_name": cls._clean_text(raw.get("equipment_name") or raw.get("name"), max_length=160),
            "equipment_brand": cls._clean_text(raw.get("equipment_brand") or raw.get("brand"), max_length=120),
            "equipment_model": cls._clean_text(
                raw.get("equipment_model")
                or raw.get("model")
                or raw.get("outdoor_unit_model")
                or raw.get("indoor_unit_model"),
                max_length=200,
            ),
            "equipment_power": cls._normalize_power(raw.get("equipment_power") or raw.get("power"), raw),
            "equipment_serial_number": cls._clean_text(
                raw.get("equipment_serial_number") or raw.get("serial_number") or raw.get("serial"),
                max_length=160,
            ),
            "equipment_inventory_number": cls._clean_text(
                raw.get("equipment_inventory_number") or raw.get("inventory_number"),
                max_length=160,
            ),
            "equipment_commissioning_date": cls._clean_text(
                raw.get("equipment_commissioning_date") or raw.get("manufactured_year"),
                max_length=80,
            ),
            "refrigerant_type": cls._normalize_refrigerant_type(raw.get("refrigerant_type") or raw.get("refrigerant")),
            "refrigerant_amount": cls._normalize_refrigerant_amount(
                raw.get("refrigerant_amount") or raw.get("refrigerant_charge")
            ),
        }
        data = {key: value for key, value in data.items() if value}

        warnings: dict[str, str] = {}
        raw_warnings = raw.get("warnings")
        if isinstance(raw_warnings, list):
            for index, warning in enumerate(raw_warnings[:5], start=1):
                cleaned = cls._clean_text(warning, max_length=200)
                if cleaned:
                    warnings[f"ai_{index}"] = cleaned
        elif raw_warnings:
            cleaned = cls._clean_text(raw_warnings, max_length=300)
            if cleaned:
                warnings["ai"] = cleaned

        if not data.get("equipment_model"):
            warnings["equipment_model"] = "Модель не распознана уверенно"
        if not data.get("equipment_serial_number"):
            warnings["equipment_serial_number"] = "Серийный номер не найден на шильдике"
        if not data.get("refrigerant_type"):
            warnings["refrigerant_type"] = "Хладагент не распознан"

        confidence = raw.get("confidence")
        try:
            confidence_value = float(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            confidence_value = None
        flags = {
            "warnings": warnings,
            "confidence": confidence_value,
            "is_valid": bool(data),
            "raw_markings": cls._clean_text(raw.get("raw_markings") or raw_text, max_length=2000),
        }
        return data, flags

    @classmethod
    async def recognize_bytes(
        cls,
        *,
        content: bytes,
        filename: Optional[str],
        mime_type: Optional[str],
    ) -> dict[str, Any]:
        if not content:
            raise ValueError("Файл пустой")
        if len(content) > CustomerRequisitesRecognitionService.MAX_FILE_SIZE_BYTES:
            raise ValueError("Файл слишком большой. Максимальный размер: 10 МБ")

        raw_text = await CustomerRequisitesRecognitionService.extract_ocr_text(
            content,
            mime_type=mime_type,
            filename=filename,
        )
        if not raw_text.strip():
            raise ValueError("Не удалось распознать текст на шильдике")
        extracted_raw = await cls.extract_nameplate(raw_text)
        extracted, validation_flags = cls.normalize_extracted(extracted_raw, raw_text)
        return {
            "raw_text": raw_text,
            "extracted": extracted,
            "validation_flags": validation_flags,
        }

    @classmethod
    def preview_merge(cls, current_repair_meta: dict[str, Any], extracted: dict[str, Any]) -> dict[str, Any]:
        applied: dict[str, Any] = {}
        conflicts: dict[str, dict[str, Any]] = {}
        skipped: dict[str, Any] = {}
        for field in cls.REPAIR_FIELDS:
            candidate = cls._clean_text(extracted.get(field), max_length=500)
            if not candidate:
                continue
            existing = cls._clean_text(current_repair_meta.get(field), max_length=500)
            if existing and existing != candidate:
                conflicts[field] = {"existing": existing, "candidate": candidate}
                continue
            if existing == candidate:
                skipped[field] = candidate
                continue
            applied[field] = candidate
        return {"applied": applied, "conflicts": conflicts, "skipped": skipped}

    @classmethod
    async def build_merge_preview(
        cls,
        session: AsyncSession,
        *,
        order_id: int,
        extracted: dict[str, Any],
    ) -> dict[str, Any] | None:
        result = await session.execute(select(Order).where(Order.id == order_id).limit(1))
        order = result.scalars().first()
        if not order:
            return None
        return cls.preview_merge(OrderService._get_repair_meta(order), extracted)

    @classmethod
    def preview_comment_merge(cls, current_repair_meta: dict[str, Any], draft_meta: dict[str, Any]) -> dict[str, Any]:
        changes: dict[str, dict[str, str]] = {}
        unchanged: dict[str, str] = {}
        for field in cls.COMMENT_FIELDS:
            candidate = cls._clean_text(draft_meta.get(field), max_length=1200)
            if not candidate:
                continue
            existing = cls._clean_text(current_repair_meta.get(field), max_length=1200)
            if existing == candidate:
                unchanged[field] = candidate
            else:
                changes[field] = {"existing": existing or "", "candidate": candidate}
        return {"changes": changes, "unchanged": unchanged}

    @classmethod
    def _comment_payload(cls, *, repair_meta: dict[str, Any], comment: str) -> ManagerRepairActAiDraftPayload:
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
        if not order or OrderService._normalize_workflow_type(getattr(order, "workflow_type", None)) != "repair":
            return None

        raw_comment = cls._clean_text(comment, max_length=4000)
        if not raw_comment:
            raise ValueError("Комментарий пустой")

        repair_meta = OrderService._get_repair_meta(order)
        ai_meta = await DefectActAIService.generate_repair_meta(
            cls._comment_payload(repair_meta=repair_meta, comment=raw_comment)
        )
        merge_preview = cls.preview_comment_merge(repair_meta, ai_meta)
        return {
            "order": cls._map_order(order),
            "comment": raw_comment,
            "repair_meta": ai_meta,
            "merge_preview": merge_preview,
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
        allowed = await cls.can_use_order(
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
                    key: cls._clean_text(value, max_length=1200)
                    for key, value in repair_meta_draft.items()
                    if cls._clean_text(value, max_length=1200)
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

    @classmethod
    async def apply_to_order(
        cls,
        session: AsyncSession,
        order_id: int,
        *,
        extracted: dict[str, Any],
        raw_text: str,
        validation_flags: dict[str, Any] | None,
        file_id: str,
        filename: str,
        mime_type: str | None,
        telegram_user_id: int | None,
        telegram_chat_id: int | None,
        telegram_message_id: int | None,
        can_attach_any: bool = False,
    ) -> dict[str, Any] | None:
        allowed = await cls.can_use_order(
            session,
            order_id,
            telegram_user_id=telegram_user_id,
            can_attach_any=can_attach_any,
        )
        if not allowed:
            return None

        result = await session.execute(
            select(Order)
            .where(Order.id == order_id)
            .options(selectinload(Order.customer))
            .limit(1)
        )
        order = result.scalars().first()
        if not order:
            return None

        repair_meta = OrderService._get_repair_meta(order)
        merge = cls.preview_merge(repair_meta, extracted)
        if merge["applied"]:
            repair_meta.update(merge["applied"])

        raw_nameplate_history = repair_meta.get(cls.HISTORY_META_KEY)
        attachments = list(raw_nameplate_history) if isinstance(raw_nameplate_history, list) else []
        attached_at = datetime.now()
        entry = BotOrderAttachmentService._build_entry(
            file_id=file_id,
            filename=filename,
            mime_type=mime_type,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            attached_at=attached_at,
        )
        entry["purpose"] = "repair_nameplate"
        entry["extracted"] = {field: extracted.get(field) for field in cls.REPAIR_FIELDS if extracted.get(field)}
        entry["validation_flags"] = validation_flags or {}
        entry["applied_fields"] = list(merge["applied"].keys())
        entry["conflicts"] = merge["conflicts"]
        entry["raw_text"] = raw_text[:4000]

        existing_index = next(
            (
                index
                for index, item in enumerate(attachments)
                if isinstance(item, dict) and item.get("file_id") == file_id
            ),
            None,
        )
        if existing_index is None:
            attachments.append(entry)
        else:
            attachments[existing_index] = entry
        repair_meta[cls.HISTORY_META_KEY] = attachments[-10:]

        meta = dict(order.technical_meta or {}) if isinstance(order.technical_meta, dict) else {}
        raw_attachments = meta.get(BotOrderAttachmentService.TELEGRAM_ATTACHMENTS_META_KEY)
        telegram_attachments = list(raw_attachments) if isinstance(raw_attachments, list) else []
        already_attached = any(
            isinstance(item, dict)
            and item.get("file_id") == file_id
            and item.get("purpose") == "repair_nameplate"
            for item in telegram_attachments
        )
        if not already_attached:
            telegram_attachments.append(
                {
                    key: value
                    for key, value in entry.items()
                    if key
                    in {
                        "source",
                        "file_id",
                        "filename",
                        "mime_type",
                        "kind",
                        "telegram_user_id",
                        "telegram_chat_id",
                        "telegram_message_id",
                        "attached_at",
                        "purpose",
                    }
                }
            )
            meta[BotOrderAttachmentService.TELEGRAM_ATTACHMENTS_META_KEY] = telegram_attachments

        OrderService._set_repair_meta(
            order,
            repair_meta,
            default_status=OrderService.REPAIR_DEFAULT_STATUS,
        )
        meta.update(order.technical_meta if isinstance(order.technical_meta, dict) else {})
        order.technical_meta = meta
        flag_modified(order, "technical_meta")
        session.add(order)
        await session.commit()
        await session.refresh(order)

        return {
            "id": int(order.id or 0),
            "applied": merge["applied"],
            "conflicts": merge["conflicts"],
            "skipped": merge["skipped"],
            "extracted": extracted,
        }
