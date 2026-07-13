from __future__ import annotations

import contextvars
import logging
import re
from typing import Any
from uuid import uuid4


REQUEST_ID_HEADER = b"x-request-id"
REQUEST_ID_MAX_LENGTH = 64
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,63}$")
_request_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id",
    default="-",
)


def current_request_id() -> str:
    return _request_id.get()


def normalize_request_id(value: str | None) -> str:
    candidate = str(value or "").strip()
    if _SAFE_REQUEST_ID.fullmatch(candidate):
        return candidate
    return uuid4().hex


class RequestContextLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = current_request_id()
        return True


class RequestContextMiddleware:
    """Attach a safe correlation id to every HTTP request and response."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        incoming_request_id: str | None = None
        for name, value in scope.get("headers") or []:
            if name.lower() == REQUEST_ID_HEADER:
                incoming_request_id = value.decode("ascii", errors="ignore")
                break

        request_id = normalize_request_id(incoming_request_id)
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        token = _request_id.set(request_id)

        async def send_with_request_id(message: dict) -> None:
            if message.get("type") == "http.response.start":
                headers = list(message.get("headers") or [])
                headers = [
                    (name, value)
                    for name, value in headers
                    if name.lower() != REQUEST_ID_HEADER
                ]
                headers.append((REQUEST_ID_HEADER, request_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            _request_id.reset(token)
