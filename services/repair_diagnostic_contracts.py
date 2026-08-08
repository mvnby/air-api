"""Strict public contracts for repair-diagnostic intake."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    field_validator,
    model_validator,
)

from core.input_validation import validate_required_phone


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

# Mirrors the storefront's conditional-question config. Values outside this
# table are rejected instead of being copied into durable metadata or AI input.
SYMPTOM_DETAIL_OPTIONS: dict[str, dict[str, frozenset[str] | None]] = {
    "water_leak": {
        "leak_timing": frozenset({"immediately", "later", "unknown"}),
        "recently_cleaned": frozenset({"yes", "no", "unknown"}),
        "drainage_exit": frozenset({"street", "sewer", "unknown"}),
        "leak_place": frozenset({"body", "wall", "tube"}),
    },
    "not_cooling": {
        "indoor_fan_works": frozenset({"yes", "no", "unknown"}),
        "outdoor_unit_starts": frozenset({"yes", "no", "unknown"}),
        "freezing_seen": frozenset({"yes", "no", "unknown"}),
        "cooled_before": frozenset({"yes", "no", "unknown"}),
    },
    "not_turning_on": {
        "has_indication": frozenset({"yes", "no", "unknown"}),
        "remote_response": frozenset({"yes", "no", "unknown"}),
        "power_checked": frozenset({"yes", "no"}),
        "voltage_surge": frozenset({"yes", "no", "unknown"}),
    },
    "error_code": {"error_code": None},
}

SYMPTOM_DETAIL_VALUE_LABELS: dict[str, dict[str, str]] = {
    "leak_timing": {
        "immediately": "Сразу",
        "later": "Через некоторое время",
        "unknown": "Не знаю",
    },
    "recently_cleaned": {"yes": "Да", "no": "Нет", "unknown": "Не знаю"},
    "drainage_exit": {
        "street": "На улицу",
        "sewer": "В канализацию",
        "unknown": "Неизвестно",
    },
    "leak_place": {"body": "Из корпуса", "wall": "По стене", "tube": "Из трубки"},
    "indoor_fan_works": {"yes": "Да", "no": "Нет", "unknown": "Не знаю"},
    "outdoor_unit_starts": {"yes": "Да", "no": "Нет", "unknown": "Не знаю"},
    "freezing_seen": {"yes": "Да", "no": "Нет", "unknown": "Не знаю"},
    "cooled_before": {"yes": "Да", "no": "Нет", "unknown": "Не знаю"},
    "has_indication": {"yes": "Да", "no": "Нет", "unknown": "Не знаю"},
    "remote_response": {"yes": "Да", "no": "Нет", "unknown": "Не знаю"},
    "power_checked": {"yes": "Да", "no": "Нет"},
    "voltage_surge": {"yes": "Да", "no": "Нет", "unknown": "Не знаю"},
}

PHOTO_FIELD_ORDER = (
    "nameplate",
    "indoor_unit",
    "outdoor_unit",
    "error_display",
    "leak_place",
)
PHOTO_LABELS = {
    "nameplate": "Фото шильдика кондиционера",
    "indoor_unit": "Фото внутреннего блока целиком",
    "outdoor_unit": "Фото наружного блока",
    "error_display": "Фото ошибки на дисплее",
    "leak_place": "Фото места протечки",
}
PHOTO_FIELDS = frozenset(PHOTO_FIELD_ORDER)

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

MAX_REPAIR_PAYLOAD_JSON_BYTES = 16 * 1024
MAX_SYMPTOM_DETAILS = 4
MAX_CLIENT_CHECKS = len(CLIENT_CHECK_LABELS)
_ERROR_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._/-]{0,31}$")


class RepairDiagnosticContact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=120)
    phone: str = Field(..., min_length=3, max_length=80)
    address: str | None = Field(default=None, max_length=300)

    @field_validator("name", "address", mode="before")
    @classmethod
    def _clean_optional_text(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("contact text fields must be strings")
        return " ".join(value.split())

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: str) -> str:
        return validate_required_phone(value)


class RepairDiagnosticLeadPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: Literal["repair"] = "repair"
    symptom: str
    problem_timing: str | None = None
    symptom_details: dict[str, StrictStr] = Field(
        default_factory=dict,
        max_length=MAX_SYMPTOM_DETAILS,
    )
    client_checks: list[StrictStr] = Field(
        default_factory=list,
        max_length=MAX_CLIENT_CHECKS,
    )
    client_comment: str | None = Field(default=None, max_length=2000)
    contact: RepairDiagnosticContact

    @field_validator("symptom")
    @classmethod
    def _validate_symptom(cls, value: str) -> str:
        if value not in SYMPTOM_LABELS:
            raise ValueError("Invalid symptom")
        return value

    @field_validator("problem_timing")
    @classmethod
    def _validate_timing(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if value not in TIMING_LABELS:
            raise ValueError("Invalid problem_timing")
        return value

    @field_validator("client_checks")
    @classmethod
    def _validate_checks(cls, value: list[str]) -> list[str]:
        if any(item not in CLIENT_CHECK_LABELS for item in value):
            raise ValueError("Invalid client_checks value")
        if len(set(value)) != len(value):
            raise ValueError("client_checks must not contain duplicates")
        if "nothing_checked" in value and len(value) > 1:
            raise ValueError("nothing_checked cannot be combined with other checks")
        return value

    @field_validator("client_comment", mode="before")
    @classmethod
    def _clean_comment(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("client_comment must be a string")
        text = " ".join(value.split())
        return text or None

    @model_validator(mode="after")
    def _validate_details_and_size(self) -> "RepairDiagnosticLeadPayload":
        allowed = SYMPTOM_DETAIL_OPTIONS.get(self.symptom, {})
        for key, raw_value in self.symptom_details.items():
            if key not in allowed:
                raise ValueError(
                    f"symptom_details.{key} is not allowed for {self.symptom}"
                )
            value = " ".join(raw_value.split())
            if not value:
                raise ValueError(f"symptom_details.{key} must not be empty")
            options = allowed[key]
            if options is not None and value not in options:
                raise ValueError(f"Invalid symptom_details.{key} value")
            if key == "error_code" and not _ERROR_CODE_PATTERN.fullmatch(value):
                raise ValueError("Invalid symptom_details.error_code value")
            self.symptom_details[key] = value
        encoded = self.model_dump_json(exclude_none=False).encode("utf-8")
        if len(encoded) > MAX_REPAIR_PAYLOAD_JSON_BYTES:
            raise ValueError("Repair diagnostic payload is too large")
        return self


class RepairDiagnosticLeadResponse(BaseModel):
    order_id: int
    status: str
    created_at: datetime
    ai_pre_diagnosis_status: str = "pending"


@dataclass(frozen=True)
class RepairDiagnosticIncomingFile:
    filename: str
    content_type: str | None
    content: bytes
    content_hash: str = ""

    def __post_init__(self) -> None:
        if not self.content_hash:
            import hashlib

            object.__setattr__(
                self,
                "content_hash",
                hashlib.sha256(self.content).hexdigest(),
            )


def parse_repair_diagnostic_payload(raw_payload: str) -> RepairDiagnosticLeadPayload:
    if not isinstance(raw_payload, str):
        raise ValueError("Repair diagnostic payload must be JSON text")
    if len(raw_payload.encode("utf-8")) > MAX_REPAIR_PAYLOAD_JSON_BYTES:
        raise ValueError("Repair diagnostic payload is too large")
    try:
        data = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise ValueError("Repair diagnostic payload must be valid JSON") from exc
    return RepairDiagnosticLeadPayload.model_validate(data)
