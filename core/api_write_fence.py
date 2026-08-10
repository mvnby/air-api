"""Fail closed for API mutations on a passive HA node."""

import json

from starlette.types import ASGIApp, Receive, Scope, Send

from core.config import settings
from core.runtime_controls import ACTIVE_APP_ROLES, normalize_app_role


_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_RESPONSE_BODY = json.dumps(
    {
        "detail": {
            "code": "api_write_fenced",
            "message": (
                "Сервер переключается на основной узел. "
                "Повторите действие через несколько секунд."
            ),
            "retryable": True,
        }
    },
    ensure_ascii=False,
    separators=(",", ":"),
).encode("utf-8")


class ApiWriteFenceMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    @staticmethod
    def _write_traffic_enabled() -> bool:
        return (
            normalize_app_role(settings.APP_ROLE) in ACTIVE_APP_ROLES
            and settings.api_ready_control_decision.enabled
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope.get("type") == "http"
            and str(scope.get("path") or "").startswith("/api/")
            and str(scope.get("method") or "").upper() in _WRITE_METHODS
            and not self._write_traffic_enabled()
        ):
            headers = [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(_RESPONSE_BODY)).encode("ascii")),
                (b"cache-control", b"no-store"),
                (b"retry-after", b"3"),
            ]
            await send(
                {
                    "type": "http.response.start",
                    "status": 503,
                    "headers": headers,
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": _RESPONSE_BODY,
                    "more_body": False,
                }
            )
            return
        await self.app(scope, receive, send)
