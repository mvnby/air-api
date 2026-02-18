from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock
from typing import Any, Optional

from core.manager_error_codes import BAD_REQUEST, VALIDATION_ERROR


@dataclass
class _TelemetryEvent:
    ts: datetime
    kind: str
    endpoint: str
    status_code: Optional[int] = None
    error_code: Optional[str] = None
    field_count: int = 0
    has_customer_id: bool = False
    has_critical_requisite_write: bool = False


class ManagerTelemetryService:
    _MAX_EVENTS = 5000
    _events: deque[_TelemetryEvent] = deque(maxlen=_MAX_EVENTS)
    _lock: Lock = Lock()

    @classmethod
    def _append(cls, event: _TelemetryEvent) -> None:
        with cls._lock:
            cls._events.append(event)

    @classmethod
    def record_error(
        cls,
        *,
        endpoint: str,
        status_code: int,
        error_code: str,
        field_errors: Optional[dict[str, str]] = None,
    ) -> None:
        cls._append(
            _TelemetryEvent(
                ts=datetime.utcnow(),
                kind="error",
                endpoint=endpoint,
                status_code=status_code,
                error_code=error_code,
                field_count=len(field_errors or {}),
            )
        )

    @classmethod
    def record_qualify_attempt(cls, *, endpoint: str, payload: Any) -> None:
        critical_keys = ("inn", "iban", "bic", "bank_name")
        has_critical = any(bool(getattr(payload, key, None)) for key in critical_keys)
        cls._append(
            _TelemetryEvent(
                ts=datetime.utcnow(),
                kind="qualify_attempt",
                endpoint=endpoint,
                has_customer_id=bool(getattr(payload, "customer_id", None)),
                has_critical_requisite_write=has_critical,
            )
        )

    @classmethod
    def record_qualify_success(cls, *, endpoint: str, payload: Any) -> None:
        critical_keys = ("inn", "iban", "bic", "bank_name")
        has_critical = any(bool(getattr(payload, key, None)) for key in critical_keys)
        cls._append(
            _TelemetryEvent(
                ts=datetime.utcnow(),
                kind="qualify_success",
                endpoint=endpoint,
                has_customer_id=bool(getattr(payload, "customer_id", None)),
                has_critical_requisite_write=has_critical,
            )
        )

    @classmethod
    def get_report(cls, *, hours: int = 24) -> dict[str, Any]:
        cutoff = datetime.utcnow() - timedelta(hours=max(hours, 1))
        with cls._lock:
            events = [event for event in cls._events if event.ts >= cutoff]

        errors = [event for event in events if event.kind == "error"]
        qualifies = [event for event in events if event.kind == "qualify_success"]
        qualify_attempts = [event for event in events if event.kind == "qualify_attempt"]

        invalid_payload_errors = [
            event
            for event in errors
            if event.status_code in (400, 422)
            and (
                event.error_code.startswith("validation_")
                or event.error_code in {BAD_REQUEST, VALIDATION_ERROR}
            )
        ]

        conflict_events = [
            event
            for event in qualify_attempts
            if event.has_customer_id and event.has_critical_requisite_write
        ]

        qualify_without_manual_overwrite = [
            event
            for event in qualifies
            if not (event.has_customer_id and event.has_critical_requisite_write)
        ]

        total_qualify = len(qualifies)
        success_wo_overwrite_pct = (
            round((len(qualify_without_manual_overwrite) / total_qualify) * 100, 2)
            if total_qualify
            else 0.0
        )

        return {
            "window_hours": max(hours, 1),
            "events_total": len(events),
            "errors_total": len(errors),
            "invalid_payload_errors": len(invalid_payload_errors),
            "requisite_conflict_attempts": len(conflict_events),
            "qualify_success_total": total_qualify,
            "qualify_success_without_manual_overwrite": len(qualify_without_manual_overwrite),
            "qualify_success_without_manual_overwrite_pct": success_wo_overwrite_pct,
        }
