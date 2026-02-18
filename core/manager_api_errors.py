from __future__ import annotations

from typing import Optional

from fastapi import HTTPException

from core.manager_error_codes import resolve_manager_error_message
from core.manager_telemetry import ManagerTelemetryService


def manager_http_error(
    *,
    status_code: int,
    endpoint: str,
    error_code: str,
    message: str | None = None,
    field_errors: Optional[dict[str, str]] = None,
) -> HTTPException:
    ManagerTelemetryService.record_error(
        endpoint=endpoint,
        status_code=status_code,
        error_code=error_code,
        field_errors=field_errors,
    )
    return HTTPException(
        status_code=status_code,
        detail={
            "message": resolve_manager_error_message(error_code, message),
            "error_code": error_code,
            "field_errors": field_errors or {},
        },
    )
