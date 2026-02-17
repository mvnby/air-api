from __future__ import annotations

from typing import Optional

from fastapi import HTTPException

from core.manager_telemetry import ManagerTelemetryService


def manager_http_error(
    *,
    status_code: int,
    endpoint: str,
    error_code: str,
    message: str,
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
            "message": message,
            "error_code": error_code,
            "field_errors": field_errors or {},
        },
    )

