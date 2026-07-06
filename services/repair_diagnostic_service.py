"""Public repair diagnostic intake for website leads."""

from __future__ import annotations

import json
import logging
import mimetypes
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select

from core.database import async_session_maker
from core.input_validation import validate_required_phone
from models import LeadSource, Order, OrderStatus
from schemas import ManagerRepairActAiDraftPayload
from services.bot_repair_nameplate_service import BotRepairNameplateService
from services.bot_service import BotService
from services.defect_act_ai_service import DefectActAIService
from services.general_media_storage_service import get_general_media_storage
from services.order_service import OrderService
from services.staff_user_service import StaffUserService

logger = logging.getLogger(__name__)


SYMPTOM_LABELS = {
    "not_cooling": "Не охлаждает / слабо охлаждает",
    "water_leak": "Течет вода из внутреннего блока",
    "not_turning_on": "Не включается",
    "turns_off": "Сам выключается",
    "noise_vibration": "Шумит или вибрирует",
    "bad_smell": "Появился неприятный запах",
    "error_code": "На дисплее ошибка",
    "other": "Другая проблема",
}

TIMING_LABELS = {
    "immediately": "Сразу после включения",
    "after_minutes": "Через несколько минут работы",
    "after_hours": "Через несколько часов",
    "constantly": "Постоянно",
    "periodically": "Периодически",
    "after_service": "После обслуживания / ремонта / переноса",
    "unknown": "Не знаю",
}

CLIENT_CHECK_LABELS = {
    "filters_cleaned": "Чистили фильтры",
    "power_restarted": "Перезагружали питание",
    "remote_batteries_changed": "Меняли батарейки в пульте",
    "drainage_checked": "Проверяли дренаж",
    "master_visited": "Уже приезжал мастер",
    "nothing_checked": "Ничего не проверяли",
}

SYMPTOM_DETAIL_LABELS = {
    "leak_timing": "Вода течет",
    "recently_cleaned": "Кондиционер недавно чистили",
    "drainage_exit": "Куда выведен дренаж",
    "leak_place": "Где капает вода",
    "indoor_fan_works": "Вентилятор внутреннего блока работает",
    "outdoor_unit_starts": "Наружный блок запускается",
    "freezing_seen": "Есть обмерзание",
    "cooled_before": "Раньше охлаждал нормально",
    "has_indication": "Есть индикация на блоке",
    "remote_response": "Реагирует на пульт",
    "power_checked": "Питание / автомат проверяли",
    "voltage_surge": "Был скачок напряжения",
    "error_code": "Код ошибки",
}

PHOTO_LABELS = {
    "nameplate": "Фото шильдика кондиционера",
    "indoor_unit": "Фото внутреннего блока целиком",
    "outdoor_unit": "Фото наружного блока",
    "error_display": "Фото ошибки на дисплее",
    "leak_place": "Фото места протечки",
}

PHOTO_FIELDS = set(PHOTO_LABELS)
ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_PHOTO_BYTES = 10 * 1024 * 1024
MAX_FILES_PER_FIELD = 5

SYMPTOM_FAULT_TYPE = {
    "not_cooling": "refrigerant_leak",
    "water_leak": "drainage_failure",
    "not_turning_on": "control_board_failure",
    "turns_off": "control_board_failure",
    "noise_vibration": "fan_motor_failure",
    "bad_smell": "contamination",
    "error_code": "unknown_fault",
    "other": "unknown_fault",
}

PRELIMINARY_DIAGNOSIS_HINTS = {
    "not_cooling": "Возможны загрязнение теплообменников, недостаток хладагента или нарушение работы наружного блока.",
    "water_leak": "Возможны засор дренажа, неправильный уклон отвода конденсата или загрязнение внутреннего блока.",
    "not_turning_on": "Возможны проблема питания, пульта, индикации или цепей управления.",
    "turns_off": "Возможны перегрев, ошибка датчика, проблема питания или защитное отключение.",
    "noise_vibration": "Возможны загрязнение, крепеж, вентилятор или вибрация блока.",
    "bad_smell": "Возможны загрязнение фильтров, теплообменника или дренажной ванны.",
    "error_code": "Код ошибки нужно расшифровать и проверить на месте.",
    "other": "Причину нужно уточнить после диагностики на месте.",
}


class RepairDiagnosticContact(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    phone: str = Field(..., min_length=3, max_length=80)
    address: Optional[str] = Field(default=None, max_length=300)

    @field_validator("name", "address", mode="before")
    @classmethod
    def _clean_optional_text(cls, value: Any) -> Any:
        if value is None:
            return None
        return " ".join(str(value).split())

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: str) -> str:
        return validate_required_phone(value)


class RepairDiagnosticLeadPayload(BaseModel):
    scenario: str = "repair"
    symptom: str
    problem_timing: Optional[str] = None
    symptom_details: Dict[str, Any] = Field(default_factory=dict)
    client_checks: List[str] = Field(default_factory=list)
    client_comment: Optional[str] = Field(default=None, max_length=2000)
    contact: RepairDiagnosticContact

    @field_validator("scenario")
    @classmethod
    def _validate_scenario(cls, value: str) -> str:
        if value != "repair":
            raise ValueError("scenario must be repair")
        return value

    @field_validator("symptom")
    @classmethod
    def _validate_symptom(cls, value: str) -> str:
        if value not in SYMPTOM_LABELS:
            allowed = ", ".join(SYMPTOM_LABELS)
            raise ValueError(f"Invalid symptom. Allowed: {allowed}")
        return value

    @field_validator("problem_timing")
    @classmethod
    def _validate_timing(cls, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        if value not in TIMING_LABELS:
            allowed = ", ".join(TIMING_LABELS)
            raise ValueError(f"Invalid problem_timing. Allowed: {allowed}")
        return value

    @field_validator("client_checks")
    @classmethod
    def _validate_checks(cls, value: List[str]) -> List[str]:
        cleaned: List[str] = []
        seen: set[str] = set()
        for item in value or []:
            if item not in CLIENT_CHECK_LABELS or item in seen:
                continue
            seen.add(item)
            cleaned.append(item)
        return cleaned

    @field_validator("client_comment", mode="before")
    @classmethod
    def _clean_comment(cls, value: Any) -> Optional[str]:
        text = " ".join(str(value or "").split())
        return text or None


class RepairDiagnosticLeadResponse(BaseModel):
    order_id: int
    status: str
    created_at: datetime
    ai_pre_diagnosis_status: str = "pending"


@dataclass(frozen=True)
class RepairDiagnosticIncomingFile:
    filename: str
    content_type: Optional[str]
    content: bytes


class RepairDiagnosticService:
    """Creates repair order leads and stores preliminary diagnostic metadata."""

    @staticmethod
    def parse_payload(raw_payload: str) -> RepairDiagnosticLeadPayload:
        try:
            return RepairDiagnosticLeadPayload.model_validate_json(raw_payload)
        except ValueError:
            data = json.loads(raw_payload)
            return RepairDiagnosticLeadPayload.model_validate(data)

    @staticmethod
    async def collect_uploads(raw_groups: Dict[str, Any]) -> Dict[str, List[RepairDiagnosticIncomingFile]]:
        uploads: Dict[str, List[RepairDiagnosticIncomingFile]] = {field: [] for field in PHOTO_FIELDS}
        for field, raw_files in raw_groups.items():
            if field not in PHOTO_FIELDS:
                continue
            files = [file for file in (raw_files or []) if file is not None]
            if len(files) > MAX_FILES_PER_FIELD:
                raise ValueError(f"{PHOTO_LABELS[field]}: можно загрузить не больше {MAX_FILES_PER_FIELD} файлов")
            for upload in files:
                content = await upload.read()
                content_type = _normalize_content_type(getattr(upload, "content_type", None))
                filename = _clean_filename(getattr(upload, "filename", None), content_type)
                _validate_photo(content=content, content_type=content_type, label=PHOTO_LABELS[field])
                uploads[field].append(
                    RepairDiagnosticIncomingFile(
                        filename=filename,
                        content_type=content_type,
                        content=content,
                    )
                )
        return uploads

    @staticmethod
    async def create_lead(
        session,
        *,
        payload: RepairDiagnosticLeadPayload,
        uploads: Dict[str, List[RepairDiagnosticIncomingFile]],
    ) -> tuple[RepairDiagnosticLeadResponse, list[RepairDiagnosticIncomingFile]]:
        comment = RepairDiagnosticService._build_order_comment(payload, uploads)
        order = await OrderService.create_from_website(
            session=session,
            customer_name=payload.contact.name,
            customer_phone=payload.contact.phone,
            customer_email=None,
            customer_address=payload.contact.address,
            items=[],
            lead_source=LeadSource.SITE,
            initial_status=OrderStatus.NEW_LEAD,
            comment=comment,
        )

        order.workflow_type = "repair"
        order.title = f"Ремонт кондиционера: {SYMPTOM_LABELS[payload.symptom]}"
        order.delivery_address = payload.contact.address

        photos = await RepairDiagnosticService._store_uploads(order_id=int(order.id), uploads=uploads)
        repair_meta = RepairDiagnosticService._build_repair_meta(payload, photos)
        meta = dict(order.technical_meta or {}) if isinstance(order.technical_meta, dict) else {}
        meta["service_type"] = "repair"
        order.technical_meta = meta
        OrderService._set_repair_meta(
            order,
            repair_meta,
            default_status=OrderService.REPAIR_DEFAULT_STATUS,
        )
        flag_modified(order, "technical_meta")

        await OrderService._maybe_add_default_repair_diagnostic(session, order)
        session.add(order)
        await session.commit()
        await session.refresh(order)

        await RepairDiagnosticService._notify_admins(session, order, payload, photos)

        response = RepairDiagnosticLeadResponse(
            order_id=int(order.id or 0),
            status=str(order.status.value if hasattr(order.status, "value") else order.status),
            created_at=order.created_at,
            ai_pre_diagnosis_status=repair_meta["ai_pre_diagnosis_status"],
        )
        nameplate_files = uploads.get("nameplate") or []
        return response, nameplate_files[:1]

    @staticmethod
    async def run_ai_pre_diagnosis(
        *,
        order_id: int,
        payload_data: Dict[str, Any],
        nameplate_files: List[RepairDiagnosticIncomingFile],
    ) -> None:
        async with async_session_maker() as session:
            result = await session.execute(select(Order).where(Order.id == order_id).limit(1))
            order = result.scalars().first()
            if not order:
                return
            payload = RepairDiagnosticLeadPayload.model_validate(payload_data)
            repair_meta = OrderService._get_repair_meta(order)
            try:
                await RepairDiagnosticService._apply_nameplate_recognition(repair_meta, nameplate_files)
                ai_meta = await RepairDiagnosticService._build_ai_meta(payload, repair_meta)
                if ai_meta:
                    repair_meta.update(ai_meta)
                repair_meta["ai_pre_diagnosis_status"] = "completed"
                repair_meta["ai_pre_diagnosis_updated_at"] = datetime.now().isoformat(timespec="seconds")
            except ValueError as exc:
                status = "skipped" if "TOKEN is not configured" in str(exc) else "failed"
                repair_meta["ai_pre_diagnosis_status"] = status
                repair_meta["ai_pre_diagnosis_error"] = str(exc)[:300]
                logger.info("Repair pre-diagnosis %s for order %s: %s", status, order_id, exc)
            except Exception as exc:  # pragma: no cover - defensive background guard
                repair_meta["ai_pre_diagnosis_status"] = "failed"
                repair_meta["ai_pre_diagnosis_error"] = str(exc)[:300]
                logger.exception("Repair pre-diagnosis failed for order %s", order_id)

            OrderService._set_repair_meta(
                order,
                repair_meta,
                default_status=OrderService.REPAIR_DEFAULT_STATUS,
            )
            flag_modified(order, "technical_meta")
            session.add(order)
            await session.commit()

    @staticmethod
    async def _store_uploads(
        *,
        order_id: int,
        uploads: Dict[str, List[RepairDiagnosticIncomingFile]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        storage = get_general_media_storage()
        stored: Dict[str, List[Dict[str, Any]]] = {field: [] for field in PHOTO_FIELDS}
        uploaded_at = datetime.now().isoformat(timespec="seconds")
        for field, files in uploads.items():
            for file in files:
                extension = _extension_for_file(file.filename, file.content_type)
                saved = await storage.save_media(
                    content=file.content,
                    namespace=f"orders/{order_id}/repair-diagnostic",
                    variant_type=field,
                    extension=extension,
                    content_type=file.content_type,
                )
                stored[field].append(
                    {
                        "filename": file.filename,
                        "content_type": file.content_type,
                        "url": saved.url,
                        "storage_provider": saved.storage_provider,
                        "storage_path": saved.path,
                        "content_hash": saved.content_hash,
                        "size_bytes": saved.size_bytes,
                        "uploaded_at": uploaded_at,
                    }
                )
        return stored

    @staticmethod
    def _build_repair_meta(
        payload: RepairDiagnosticLeadPayload,
        photos: Dict[str, List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        missing = RepairDiagnosticService._missing_data(payload, photos)
        symptom_label = SYMPTOM_LABELS[payload.symptom]
        return {
            "scenario": "repair",
            "repair_status": OrderService.REPAIR_DEFAULT_STATUS,
            "symptom": payload.symptom,
            "symptom_label": symptom_label,
            "symptom_details": _clean_nested_dict(payload.symptom_details),
            "problem_timing": payload.problem_timing,
            "problem_timing_label": TIMING_LABELS.get(payload.problem_timing or "", ""),
            "client_checks": payload.client_checks,
            "client_checks_labels": [CLIENT_CHECK_LABELS[item] for item in payload.client_checks],
            "photos": photos,
            "client_comment": payload.client_comment or "",
            "contact": payload.contact.model_dump(),
            "ai_pre_diagnosis_status": "pending",
            "missing_data": missing,
            "customer_complaint": f"Клиент сообщил: {symptom_label}.",
            "complaint_official": f"Со слов клиента: {symptom_label.lower()}.",
            "likely_diagnosis": PRELIMINARY_DIAGNOSIS_HINTS[payload.symptom],
            "preliminary_fault_type": SYMPTOM_FAULT_TYPE[payload.symptom],
            "preliminary_note": (
                "Предварительная оценка основана на ответах клиента. "
                "Точная причина и стоимость ремонта определяются после диагностики на месте."
            ),
        }

    @staticmethod
    def _build_order_comment(
        payload: RepairDiagnosticLeadPayload,
        uploads: Dict[str, List[RepairDiagnosticIncomingFile]],
    ) -> str:
        lines = [
            "Заявка на ремонт кондиционера с предварительной диагностикой.",
            f"Что случилось: {SYMPTOM_LABELS[payload.symptom]}",
        ]
        if payload.problem_timing:
            lines.append(f"Когда проявляется: {TIMING_LABELS[payload.problem_timing]}")
        if payload.client_checks:
            labels = [CLIENT_CHECK_LABELS[item] for item in payload.client_checks]
            lines.append(f"Что уже проверяли: {', '.join(labels)}")
        detail_lines = RepairDiagnosticService._format_details(payload.symptom_details)
        if detail_lines:
            lines.append("Уточнения:")
            lines.extend(f"- {line}" for line in detail_lines)
        photo_lines = [
            f"{PHOTO_LABELS[field]}: {len(files)}"
            for field, files in uploads.items()
            if files
        ]
        if photo_lines:
            lines.append(f"Фото: {', '.join(photo_lines)}")
        if payload.client_comment:
            lines.append(f"Комментарий клиента: {payload.client_comment}")
        if payload.contact.address:
            lines.append(f"Адрес/район: {payload.contact.address}")
        return "\n".join(lines)

    @staticmethod
    def _format_details(details: Dict[str, Any]) -> List[str]:
        result: List[str] = []
        cleaned = _clean_nested_dict(details)
        for key, value in cleaned.items():
            label = SYMPTOM_DETAIL_LABELS.get(key, key)
            result.append(f"{label}: {_stringify_detail(value)}")
        return result

    @staticmethod
    def _missing_data(
        payload: RepairDiagnosticLeadPayload,
        photos: Dict[str, List[Dict[str, Any]]],
    ) -> List[str]:
        missing: List[str] = []
        if not photos.get("nameplate"):
            missing.append("Фото шильдика")
        if not photos.get("indoor_unit"):
            missing.append("Фото внутреннего блока целиком")
        if payload.symptom == "water_leak" and not photos.get("leak_place"):
            missing.append("Фото места протечки")
        if payload.symptom == "error_code":
            if not payload.symptom_details.get("error_code"):
                missing.append("Код ошибки")
            if not photos.get("error_display"):
                missing.append("Фото ошибки на дисплее")
        if not payload.contact.address:
            missing.append("Адрес или район")
        return missing

    @staticmethod
    async def _apply_nameplate_recognition(
        repair_meta: Dict[str, Any],
        nameplate_files: List[RepairDiagnosticIncomingFile],
    ) -> None:
        if not nameplate_files:
            repair_meta["nameplate_recognition_status"] = "missing_photo"
            return
        file = nameplate_files[0]
        try:
            recognized = await BotRepairNameplateService.recognize_bytes(
                content=file.content,
                filename=file.filename,
                mime_type=file.content_type,
            )
        except Exception as exc:
            repair_meta["nameplate_recognition_status"] = "failed"
            repair_meta["nameplate_recognition_error"] = str(exc)[:300]
            return

        extracted = recognized.get("extracted") if isinstance(recognized, dict) else {}
        if not isinstance(extracted, dict):
            extracted = {}
        merge = BotRepairNameplateService.preview_merge(repair_meta, extracted)
        if merge["applied"]:
            repair_meta.update(merge["applied"])
        repair_meta["nameplate_recognition_status"] = "recognized"
        repair_meta["nameplate_recognition"] = {
            "filename": file.filename,
            "extracted": extracted,
            "validation_flags": recognized.get("validation_flags") or {},
            "applied_fields": list(merge["applied"].keys()),
            "conflicts": merge["conflicts"],
        }

    @staticmethod
    async def _build_ai_meta(
        payload: RepairDiagnosticLeadPayload,
        repair_meta: Dict[str, Any],
    ) -> Dict[str, Any]:
        diagnostic_context = RepairDiagnosticService._build_order_comment(
            payload,
            {field: [] for field in PHOTO_FIELDS},
        )
        return await DefectActAIService.generate_repair_meta(
            ManagerRepairActAiDraftPayload(
                defect_type=SYMPTOM_FAULT_TYPE[payload.symptom],
                defect_label=SYMPTOM_LABELS[payload.symptom],
                allow_assumptions=False,
                polish_existing=False,
                equipment_name=repair_meta.get("equipment_name"),
                equipment_brand=repair_meta.get("equipment_brand"),
                equipment_model=repair_meta.get("equipment_model"),
                equipment_power=repair_meta.get("equipment_power"),
                customer_complaint=repair_meta.get("customer_complaint"),
                complaint_official=repair_meta.get("complaint_official"),
                likely_diagnosis=repair_meta.get("likely_diagnosis"),
                extra_context=diagnostic_context,
                current_meta=repair_meta,
            )
        )

    @staticmethod
    async def _notify_admins(
        session,
        order: Order,
        payload: RepairDiagnosticLeadPayload,
        photos: Dict[str, List[Dict[str, Any]]],
    ) -> None:
        admin_ids = await StaffUserService.get_active_owner_admin_telegram_recipient_ids(session)
        if not admin_ids:
            return
        photo_count = sum(len(items) for items in photos.values())
        message_lines = [
            f"<b>ЗАЯВКА НА РЕМОНТ С САЙТА #{order.id}</b>",
            f"Клиент: {payload.contact.name}",
            f"Телефон: {payload.contact.phone}",
            f"Симптом: {SYMPTOM_LABELS[payload.symptom]}",
        ]
        if payload.contact.address:
            message_lines.append(f"Адрес/район: {payload.contact.address}")
        message_lines.append(f"Фото: {photo_count}")
        admin_text = "\n".join(message_lines)
        for admin_id in admin_ids:
            try:
                await BotService.send_message(admin_id, admin_text)
            except Exception as exc:
                logger.warning("Failed to notify admin %s about repair order %s: %s", admin_id, order.id, exc)


def _normalize_content_type(value: Optional[str]) -> str:
    return str(value or "").split(";")[0].strip().lower()


def _clean_filename(filename: Optional[str], content_type: Optional[str]) -> str:
    raw = str(filename or "").replace("\\", "/").split("/")[-1].strip()
    if raw:
        return raw[:160]
    extension = _extension_for_file("", content_type)
    return f"repair-photo.{extension}"


def _extension_for_file(filename: str, content_type: Optional[str]) -> str:
    lower = str(filename or "").lower()
    if "." in lower:
        extension = lower.rsplit(".", 1)[-1].strip()
        if extension in {"jpg", "jpeg", "png", "webp"}:
            return "jpg" if extension == "jpeg" else extension
    guessed = mimetypes.guess_extension(content_type or "") or ".jpg"
    return guessed.lower().lstrip(".").replace("jpeg", "jpg") or "jpg"


def _validate_photo(*, content: bytes, content_type: str, label: str) -> None:
    if not content:
        raise ValueError(f"{label}: файл пустой")
    if len(content) > MAX_PHOTO_BYTES:
        raise ValueError(f"{label}: файл больше 10 МБ")
    if content_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise ValueError(f"{label}: поддерживаются только JPG, PNG и WEBP")


def _clean_nested_dict(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    cleaned: Dict[str, Any] = {}
    for key, value in raw.items():
        clean_key = " ".join(str(key or "").split())[:80]
        if not clean_key or value is None:
            continue
        if isinstance(value, str):
            text = " ".join(value.split())[:500]
            if text:
                cleaned[clean_key] = text
        elif isinstance(value, bool):
            cleaned[clean_key] = value
        elif isinstance(value, (int, float)):
            cleaned[clean_key] = value
        elif isinstance(value, list):
            items = [str(item).strip()[:160] for item in value if str(item).strip()]
            if items:
                cleaned[clean_key] = items[:20]
    return cleaned


def _stringify_detail(value: Any) -> str:
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)
