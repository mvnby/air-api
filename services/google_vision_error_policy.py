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
    if 500 <= status <= 599:
        return "upstream_error", True
    if 400 <= status <= 499:
        return "request_rejected", False
    return "unclassified_response", False


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
        "FAILED_PRECONDITION": "failed_precondition",
        "UNAUTHENTICATED": "credentials_rejected",
        "PERMISSION_DENIED": "credentials_rejected",
    }
    retryable_codes = {
        "RESOURCE_EXHAUSTED": "rate_limited",
        "DEADLINE_EXCEEDED": "upstream_error",
        "ABORTED": "upstream_error",
        "INTERNAL": "upstream_error",
        "UNAVAILABLE": "upstream_error",
    }
    if rpc_status in terminal_codes:
        code, retryable = terminal_codes[rpc_status], False
    elif rpc_status in retryable_codes:
        code, retryable = retryable_codes[rpc_status], True
    elif not rpc_status and status in {3, 7, 9, 16}:
        if status == 3:
            code = "invalid_argument"
        elif status == 9:
            code = "failed_precondition"
        else:
            code = "credentials_rejected"
        retryable = False
    elif not rpc_status and status in {4, 8, 10, 13, 14}:
        code = "rate_limited" if status == 8 else "upstream_error"
        retryable = True
    else:
        # Unknown names, conflicting encodings, missing fields, and malformed
        # canonical statuses are terminal. Retrying is reserved exclusively
        # for the explicit transient allowlists above.
        code, retryable = "unclassified_response", False
    return OcrProviderError(
        "Google Vision rejected the OCR request",
        retryable=retryable,
        code=code,
        status=status or None,
    )
