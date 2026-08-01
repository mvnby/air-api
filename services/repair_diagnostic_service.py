"""Public repair diagnostic intake for website leads."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

from core.public_upload_limits import PUBLIC_ATTACHMENT_PAYLOAD_MAX_BYTES
from core.public_image_validation import (
    PUBLIC_IMAGE_FORMAT_BY_MIME,
    validate_public_image,
)
from services.order_service import OrderService
from services.repair_diagnostic_contracts import (
    CLIENT_CHECK_LABELS,
    PHOTO_FIELD_ORDER,
    PHOTO_FIELDS,
    PHOTO_LABELS,
    SYMPTOM_DETAIL_LABELS,
    SYMPTOM_FAULT_TYPE,
    SYMPTOM_LABELS,
    TIMING_LABELS,
    RepairDiagnosticIncomingFile,
    RepairDiagnosticLeadPayload,
    RepairDiagnosticLeadResponse,
    parse_repair_diagnostic_payload,
)


ALLOWED_IMAGE_MIME_TYPES = frozenset(PUBLIC_IMAGE_FORMAT_BY_MIME)
MAX_PHOTO_BYTES = 10 * 1024 * 1024
MAX_FILES_PER_FIELD = 5
MAX_PAYLOAD_BYTES = PUBLIC_ATTACHMENT_PAYLOAD_MAX_BYTES

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


class RepairDiagnosticService:
    """Creates repair order leads and stores preliminary diagnostic metadata."""

    @staticmethod
    def parse_payload(raw_payload: str) -> RepairDiagnosticLeadPayload:
        return parse_repair_diagnostic_payload(raw_payload)

    @staticmethod
    async def collect_uploads(raw_groups: Dict[str, Any]) -> Dict[str, List[RepairDiagnosticIncomingFile]]:
        uploads: Dict[str, List[RepairDiagnosticIncomingFile]] = {
            field: [] for field in PHOTO_FIELD_ORDER
        }
        total_bytes = 0
        for field, raw_files in raw_groups.items():
            if field not in PHOTO_FIELDS:
                continue
            files = [file for file in (raw_files or []) if file is not None]
            if len(files) > MAX_FILES_PER_FIELD:
                raise ValueError(f"{PHOTO_LABELS[field]}: можно загрузить не больше {MAX_FILES_PER_FIELD} файлов")
            for upload in files:
                content = await upload.read(MAX_PHOTO_BYTES + 1)
                content_type = _normalize_content_type(getattr(upload, "content_type", None))
                filename = _clean_filename(getattr(upload, "filename", None), content_type)
                total_bytes += len(content)
                if total_bytes > MAX_PAYLOAD_BYTES:
                    raise ValueError(
                        "Общий размер фотографий не должен превышать "
                        f"{MAX_PAYLOAD_BYTES // (1024 * 1024)} МБ"
                    )
                await _validate_photo(
                    content=content,
                    content_type=content_type,
                    label=PHOTO_LABELS[field],
                )
                uploads[field].append(
                    RepairDiagnosticIncomingFile(
                        filename=filename,
                        content_type=content_type,
                        content=content,
                        content_hash=hashlib.sha256(content).hexdigest(),
                    )
                )
        return uploads

    @staticmethod
    def _payload_from_repair_meta(repair_meta: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "scenario": "repair",
            "symptom": repair_meta.get("symptom"),
            "problem_timing": repair_meta.get("problem_timing"),
            "symptom_details": repair_meta.get("symptom_details") or {},
            "client_checks": repair_meta.get("client_checks") or [],
            "client_comment": repair_meta.get("client_comment") or None,
            "contact": repair_meta.get("contact") or {},
        }

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

def _normalize_content_type(value: Optional[str]) -> str:
    return str(value or "").split(";")[0].strip().lower()


def _clean_filename(filename: Optional[str], content_type: Optional[str]) -> str:
    raw = str(filename or "").replace("\\", "/").split("/")[-1].strip()
    if raw:
        return raw[:160]
    extension = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }.get(str(content_type or ""), "jpg")
    return f"repair-photo.{extension}"


async def _validate_photo(
    *,
    content: bytes,
    content_type: str,
    label: str,
) -> None:
    await validate_public_image(
        filename=label,
        content_type=content_type,
        content=content,
        max_bytes=MAX_PHOTO_BYTES,
    )


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
