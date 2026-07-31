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
from models import (
    Customer,
    Order,
    OrderInstaller,
    OrderStatus,
    OrderWorkStage,
    StaffUser,
    TenantMembership,
)
from models.tenancy import TenantScope
from services.bot_order_attachment_service import BotOrderAttachmentService
from services.customer_requisites_recognition_service import CustomerRequisitesRecognitionService
from services.order_service import OrderService
from services.private_attachment_storage_service import sha256_bytes
from services.service_attachment_service import ServiceAttachmentService
from services.staff_user_service import StaffUserService
from services.tenant_entity_access_service import TenantEntityAccessService
from services.tenant_scope_service import tenant_scope_clause


class BotRepairNameplateService:
    """Recognizes AC nameplates and safely applies passport fields to repair orders."""

    TCL_YEAR_BASE = 2010
    TCL_UNIT_TYPE_LABELS = {
        "W": "наружный блок",
        "N": "внутренний блок",
        "Z": "оконный/моноблок",
    }
    TCL_PRODUCT_MARK_LABELS = {
        "S": "SKD-компоненты",
        "Z": "собранный блок",
    }
    ACTIVE_REPAIR_STATUSES = (
        OrderStatus.NEW_LEAD,
        OrderStatus.NEGOTIATION,
        OrderStatus.EXECUTION,
    )
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

    @staticmethod
    def _clean_text(value: Any, *, max_length: int = 500) -> Optional[str]:
        text = str(value or "").strip()
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[:max_length].strip() or None

    @classmethod
    def _clean_serial_candidate(cls, value: Any) -> Optional[str]:
        text = cls._clean_text(value, max_length=240)
        if not text:
            return None
        text = text.upper().strip(" .,:;")
        text = re.sub(r"\s+", " ", text)
        comparable = re.sub(r"[^A-Z0-9]", "", text)
        if len(comparable) < 5:
            return None
        if "/" in text:
            return None
        return text

    @classmethod
    def _serial_candidate_tokens(cls, value: Any) -> list[str]:
        text = cls._clean_text(value, max_length=4000)
        if not text:
            return []
        candidates = []
        if "\n" not in text and len(text) <= 80 and not re.search(
            r"\b(MODEL|МОДЕЛЬ|REFRIGERANT|CAPACITY|МОЩНОСТЬ)\b",
            text,
            flags=re.IGNORECASE,
        ):
            candidates.append(text)
        candidates.extend(re.findall(r"\b[A-Z0-9][A-Z0-9/-]{5,}[A-Z0-9]\b", text, flags=re.IGNORECASE))
        cleaned: list[str] = []
        for candidate in candidates:
            normalized = cls._clean_serial_candidate(candidate)
            if normalized:
                cleaned.append(normalized)
        return cleaned

    @staticmethod
    def _serial_identity(value: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", value.upper())

    @classmethod
    def _collect_serial_candidates(
        cls,
        raw: dict[str, Any],
        raw_text: str,
        *,
        equipment_model: str | None,
    ) -> list[str]:
        values: list[Any] = []
        for key in (
            "equipment_serial_number",
            "serial_number",
            "serial",
            "sn",
            "s_n",
            "barcode_text",
            "barcode_value",
            "barcode",
        ):
            values.append(raw.get(key))

        for key in (
            "serial_candidates",
            "serial_number_candidates",
            "serials",
            "barcode_values",
            "barcodes",
            "raw_markings",
        ):
            value = raw.get(key)
            if isinstance(value, list):
                values.extend(value)
            elif isinstance(value, dict):
                values.extend(value.values())
            else:
                values.append(value)
        values.append(raw_text)

        model_identity = cls._serial_identity(equipment_model or "")
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            for candidate in cls._serial_candidate_tokens(value):
                identity = cls._serial_identity(candidate)
                if (
                    not identity
                    or identity == model_identity
                    or bool(model_identity and identity in model_identity)
                    or identity in seen
                ):
                    continue
                seen.add(identity)
                result.append(candidate)
        return result

    @classmethod
    def _serial_candidate_score(cls, candidate: str, *, brand: str | None, model: str | None) -> int:
        identity = cls._serial_identity(candidate)
        score = min(len(identity), 30)
        has_letters = bool(re.search(r"[A-Z]", identity))
        has_digits = bool(re.search(r"\d", identity))
        if has_letters and has_digits:
            score += 25
        if len(identity) >= 18:
            score += 35
        elif len(identity) >= 14:
            score += 20
        elif len(identity) <= 10 and identity.isdigit():
            score -= 20

        brand_text = (brand or "").upper()
        model_text = (model or "").upper()
        looks_like_tcl = "TCL" in brand_text or model_text.startswith("TAC-")
        if looks_like_tcl:
            if has_letters and has_digits and len(identity) >= 18:
                score += 60
            if re.fullmatch(r"MO\d+", identity):
                score -= 60
            if identity.isdigit() and len(identity) <= 12:
                score -= 35
        elif re.fullmatch(r"MO\d+", identity):
            score -= 25
        return score

    @classmethod
    def _select_serial_candidate(
        cls,
        candidates: list[str],
        *,
        brand: str | None,
        model: str | None,
    ) -> Optional[str]:
        if not candidates:
            return None
        return max(candidates, key=lambda candidate: cls._serial_candidate_score(candidate, brand=brand, model=model))

    @classmethod
    def _decode_tcl_year(cls, value: str) -> Optional[int]:
        if not re.fullmatch(r"[A-Z]", value):
            return None
        return cls.TCL_YEAR_BASE + (ord(value) - ord("A"))

    @staticmethod
    def _decode_tcl_month(value: str) -> Optional[int]:
        if value in {"1", "2", "3", "4", "5", "6", "7", "8", "9"}:
            return int(value)
        return {"A": 10, "B": 11, "C": 12}.get(value)

    @classmethod
    def _decode_tcl_month_code(cls, value: str) -> tuple[Optional[int], Optional[int]]:
        if len(value) != 2:
            return None, None
        return cls._decode_tcl_year(value[0]), cls._decode_tcl_month(value[1])

    @classmethod
    def _decode_tcl_date_code(cls, value: str) -> tuple[Optional[int], Optional[int], Optional[int]]:
        if len(value) != 4:
            return None, None, None
        year = cls._decode_tcl_year(value[0])
        month = cls._decode_tcl_month(value[1])
        day = int(value[2:4]) if value[2:4].isdigit() else None
        if day is not None and not 1 <= day <= 31:
            day = None
        return year, month, day

    @classmethod
    def _decode_tcl_factory_serial(cls, serial: str | None) -> Optional[dict[str, Any]]:
        identity = cls._serial_identity(serial or "")
        if len(identity) != 20:
            return None

        manufacturer_code = identity[0]
        model_code = identity[1:5]
        unit_code = identity[5]
        order_code = identity[6:8]
        batch_code = identity[8:10]
        product_mark_code = identity[10]
        production_code = identity[11:15]
        running_number = identity[15:20]

        if manufacturer_code != "1":
            return None
        if unit_code not in cls.TCL_UNIT_TYPE_LABELS:
            return None
        if product_mark_code not in cls.TCL_PRODUCT_MARK_LABELS:
            return None
        if not running_number.isdigit():
            return None

        order_year, order_month = cls._decode_tcl_month_code(order_code)
        production_year, production_month, production_day = cls._decode_tcl_date_code(production_code)
        if not all([order_year, order_month, production_year, production_month, production_day]):
            return None

        return {
            "format": "tcl_factory_20",
            "manufacturer_code": manufacturer_code,
            "model_code": model_code,
            "unit_type_code": unit_code,
            "unit_type_label": cls.TCL_UNIT_TYPE_LABELS[unit_code],
            "order_date_code": order_code,
            "order_year": order_year,
            "order_month": order_month,
            "batch_code": batch_code,
            "product_mark_code": product_mark_code,
            "product_mark_label": cls.TCL_PRODUCT_MARK_LABELS[product_mark_code],
            "production_date_code": production_code,
            "production_date": f"{production_year:04d}-{production_month:02d}-{production_day:02d}",
            "product_serial_number": running_number,
        }

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
    def _is_active_repair_order(cls, order: Order | None) -> bool:
        if not order:
            return False
        workflow_type = OrderService._normalize_workflow_type(getattr(order, "workflow_type", None))
        return workflow_type == "repair" and order.status in cls.ACTIVE_REPAIR_STATUSES

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
    async def _legacy_installer_id(
        cls,
        session: AsyncSession,
        telegram_user_id: int | str | None,
        *,
        tenant_scope: TenantScope,
    ) -> Optional[int]:
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
            .join(
                TenantMembership,
                TenantMembership.staff_user_id == StaffUser.id,
            )
            .where(
                TenantMembership.tenant_id == tenant_scope.tenant_id,
                TenantMembership.status == "active",
            )
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
        tenant_scope: TenantScope,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(Order)
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .where(Order.status.in_(list(cls.ACTIVE_REPAIR_STATUSES)))
            .where(Order.workflow_type == "repair")
            .where(tenant_scope_clause(Order, tenant_scope))
            .where(TenantEntityAccessService.order_customer_clause(tenant_scope))
            .options(selectinload(Order.customer))
            .order_by(Order.updated_at.desc(), Order.created_at.desc(), Order.id.desc())
            .limit(max(1, min(limit, 10)))
        )

        if not can_attach_any:
            installer_id = await cls._legacy_installer_id(
                session,
                telegram_user_id,
                tenant_scope=tenant_scope,
            )
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
        tenant_scope: TenantScope,
    ) -> bool:
        order = await TenantEntityAccessService.get_order(
            session,
            order_id,
            tenant_scope=tenant_scope,
        )
        if not cls._is_active_repair_order(order):
            return False
        if can_attach_any:
            return True
        return await BotOrderAttachmentService.can_attach_to_order(
            session,
            order_id,
            telegram_user_id=telegram_user_id,
            tenant_scope=tenant_scope,
        )

    @classmethod
    def build_extraction_prompt(cls, raw_text: str) -> str:
        return (
            "Ты извлекаешь данные с шильдика кондиционера для дефектного акта ремонта.\n"
            "Верни только JSON-объект без markdown. Не выдумывай данные: если поле не видно, верни null.\n\n"
            "Ключи JSON:\n"
            "equipment_name, equipment_brand, equipment_model, equipment_power, equipment_serial_number, "
            "equipment_inventory_number, equipment_commissioning_date, refrigerant_type, refrigerant_amount, "
            "unit_type, capacity_btu, cooling_capacity_kw, serial_candidates, raw_markings, confidence, warnings.\n\n"
            "Правила:\n"
            "- equipment_name: человекочитаемо, например 'Кондиционер, наружный блок' или 'Кондиционер'.\n"
            "- equipment_model: модель блока ровно как на шильдике.\n"
            "- equipment_serial_number: серийный номер/SN/Serial No, только если он явно виден.\n"
            "- serial_candidates: если на наклейке несколько похожих номеров, верни массив всех вариантов.\n"
            "- Для TCL/TAC часто серийный номер — длинный буквенно-цифровой код под штрихкодом; короткие MO/даты/партии не выбирай серийником, если есть длинный код.\n"
            "- Для TCL factory SN формата 20 символов учитывай сегменты: 1 + 4 + W/N/Z + год/месяц заказа + batch + S/Z + год/месяц/день производства + 5 цифр серийного номера.\n"
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
        serial_candidates = cls._collect_serial_candidates(
            raw,
            raw_text,
            equipment_model=data.get("equipment_model"),
        )
        selected_serial = cls._select_serial_candidate(
            serial_candidates,
            brand=data.get("equipment_brand"),
            model=data.get("equipment_model"),
        )
        if selected_serial:
            data["equipment_serial_number"] = selected_serial
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
        elif len(serial_candidates) > 1:
            warnings["serial_candidates"] = (
                "Нашел несколько похожих номеров; выбрал наиболее вероятный серийник, проверьте перед записью"
            )
        if not data.get("refrigerant_type"):
            warnings["refrigerant_type"] = "Хладагент не распознан"

        confidence = raw.get("confidence")
        try:
            confidence_value = float(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            confidence_value = None
        serial_candidates = sorted(
            serial_candidates,
            key=lambda candidate: cls._serial_candidate_score(
                candidate,
                brand=data.get("equipment_brand"),
                model=data.get("equipment_model"),
            ),
            reverse=True,
        )
        flags = {
            "warnings": warnings,
            "confidence": confidence_value,
            "is_valid": bool(data),
            "raw_markings": cls._clean_text(raw.get("raw_markings") or raw_text, max_length=2000),
        }
        if serial_candidates:
            flags["serial_candidates"] = serial_candidates[:8]
        serial_details = cls._decode_tcl_factory_serial(data.get("equipment_serial_number"))
        if serial_details:
            flags["serial_details"] = serial_details
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
        tenant_scope: TenantScope,
    ) -> dict[str, Any] | None:
        order = await TenantEntityAccessService.get_order(
            session,
            order_id,
            tenant_scope=tenant_scope,
        )
        if not order:
            return None
        return cls.preview_merge(OrderService._get_repair_meta(order), extracted)

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
        file_content: bytes | None = None,
        tenant_scope: TenantScope,
    ) -> dict[str, Any] | None:
        allowed = await cls.can_use_order(
            session,
            order_id,
            telegram_user_id=telegram_user_id,
            can_attach_any=can_attach_any,
            tenant_scope=tenant_scope,
        )
        if not allowed:
            return None

        order = await TenantEntityAccessService.get_order(
            session,
            order_id,
            tenant_scope=tenant_scope,
            options=(selectinload(Order.customer),),
            for_update=True,
        )
        if not order:
            return None

        repair_meta = OrderService._get_repair_meta(order)
        merge = cls.preview_merge(repair_meta, extracted)
        if merge["applied"]:
            repair_meta.update(merge["applied"])

        model_candidates: list[str] = []
        raw_models = repair_meta.get("equipment_models")
        if isinstance(raw_models, list):
            model_candidates.extend(str(item) for item in raw_models)
        model_candidates.extend(
            str(value)
            for value in (repair_meta.get("equipment_model"), extracted.get("equipment_model"))
            if value
        )
        equipment_models: list[str] = []
        seen_models: set[str] = set()
        for value in model_candidates:
            model = cls._clean_text(value, max_length=200)
            if not model or model.casefold() in seen_models:
                continue
            seen_models.add(model.casefold())
            equipment_models.append(model)
        if equipment_models:
            repair_meta["equipment_models"] = equipment_models[:4]

        raw_nameplate_history = repair_meta.get(cls.HISTORY_META_KEY)
        attachments = list(raw_nameplate_history) if isinstance(raw_nameplate_history, list) else []
        attached_at = datetime.now()
        storage_meta: dict[str, Any] = {}
        if file_content:
            await ServiceAttachmentService.create_and_link_order_attachment(
                session,
                order_id=order_id,
                content=file_content,
                filename=filename,
                mime_type=mime_type,
                category="nameplate",
                source="telegram_bot",
                transcript=raw_text,
                captured_at=attached_at,
                telegram_meta={
                    "file_id": file_id,
                    "user_id": telegram_user_id,
                    "chat_id": telegram_chat_id,
                    "message_id": telegram_message_id,
                    "source_meta": {"purpose": "repair_nameplate"},
                },
                tenant_scope=tenant_scope,
            )
            storage_meta = {
                "storage_provider": "private_service_attachment",
                "content_hash": sha256_bytes(file_content),
                "size_bytes": len(file_content),
            }
        entry = BotOrderAttachmentService._build_entry(
            file_id=file_id,
            filename=filename,
            mime_type=mime_type,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            attached_at=attached_at,
            **storage_meta,
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
        telegram_attachments, _ = BotOrderAttachmentService.upsert_telegram_attachment(meta, entry)

        OrderService._set_repair_meta(
            order,
            repair_meta,
            default_status=OrderService.REPAIR_DEFAULT_STATUS,
        )
        updated_meta = dict(order.technical_meta or {}) if isinstance(order.technical_meta, dict) else {}
        updated_meta[BotOrderAttachmentService.TELEGRAM_ATTACHMENTS_META_KEY] = telegram_attachments
        order.technical_meta = updated_meta
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
