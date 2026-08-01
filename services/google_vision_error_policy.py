"""Typed retry policy for Google Vision transport and response failures."""

from __future__ import annotations

from typing import Any

from googleapiclient.errors import HttpError


class OcrProviderError(ValueError):
    """Privacy-safe OCR infrastructure or configuration failure."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
        code: str,
        status: int | None = None,
    ) -> None:
        self.retryable = bool(retryable)
        self.code = str(code)[:100]
        self.status = status
        super().__init__(str(message)[:500])


def google_vision_status_contract(status: int) -> tuple[str, bool]:
    if status == 400:
        return "invalid_argument", False
    if status in {401, 403}:
        return "credentials_rejected", False
    if status == 429:
        return "rate_limited", True
    if status >= 500:
        return "upstream_error", True
    if status >= 400:
        return "request_rejected", False
    return "upstream_error", True


def google_vision_http_error(error: HttpError) -> OcrProviderError:
    try:
        status = int(getattr(error.resp, "status", 0) or 0)
    except (TypeError, ValueError):
        status = 0
    code, retryable = google_vision_status_contract(status)
    return OcrProviderError(
        f"Google Vision returned HTTP {status or 'unknown'}",
        retryable=retryable,
        code=code,
        status=status or None,
    )


def google_vision_rpc_error(error: dict[str, Any]) -> OcrProviderError:
    rpc_status = str(error.get("status") or "").strip().upper()
    try:
        status = int(error.get("code") or 0)
    except (TypeError, ValueError):
        status = 0
    terminal_codes = {
        "INVALID_ARGUMENT": "invalid_argument",
        "UNAUTHENTICATED": "credentials_rejected",
        "PERMISSION_DENIED": "credentials_rejected",
    }
    retryable_codes = {
        "RESOURCE_EXHAUSTED": "rate_limited",
        "DEADLINE_EXCEEDED": "upstream_error",
        "INTERNAL": "upstream_error",
        "UNAVAILABLE": "upstream_error",
    }
    if rpc_status in terminal_codes:
        code, retryable = terminal_codes[rpc_status], False
    elif rpc_status in retryable_codes:
        code, retryable = retryable_codes[rpc_status], True
    elif status in {3, 7, 16}:
        code = "invalid_argument" if status == 3 else "credentials_rejected"
        retryable = False
    elif status in {4, 8, 13, 14}:
        code = "rate_limited" if status == 8 else "upstream_error"
        retryable = True
    else:
        code, retryable = google_vision_status_contract(status)
    return OcrProviderError(
        "Google Vision rejected the OCR request",
        retryable=retryable,
        code=code,
        status=status or None,
    )
