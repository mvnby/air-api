from __future__ import annotations

from hashlib import sha256

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from core.config import settings
from core.storefront_request_auth import (
    STOREFRONT_VERIFIED_ENVELOPE_SCOPE_KEY,
    StorefrontEnvelopeAuthConfig,
    authenticate_storefront_envelope,
    resolve_allowed_api_hostname,
    resolve_idempotency_key_binding,
)
from core.storefront_request_envelope import (
    force_private_storefront_response_headers,
    storefront_signing_header_state,
)
from core.storefront_public_routes import requires_storefront_gateway


class _StorefrontBodyTooLarge(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=413,
            detail="Storefront request body is too large",
        )


class StorefrontRequestGatewayMiddleware:
    """Authenticate signed storefront requests before FastAPI parses them."""

    def __init__(self, app: ASGIApp, *, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = int(max_body_bytes)

    @staticmethod
    def _content_length(raw_headers: tuple[tuple[bytes, bytes], ...]) -> int | None:
        values = [
            value for name, value in raw_headers if name.lower() == b"content-length"
        ]
        if not values:
            return None
        if len(values) != 1:
            raise ValueError("ambiguous content length")
        try:
            raw_value = values[0].decode("ascii")
        except UnicodeDecodeError as exc:
            raise ValueError("invalid content length") from exc
        if not raw_value.isdigit() or (
            raw_value != "0" and raw_value.startswith("0")
        ):
            raise ValueError("invalid content length")
        return int(raw_value)

    def _limited_receive(self, receive: Receive) -> Receive:
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] != "http.request":
                return message
            received += len(bytes(message.get("body", b"")))
            if received > self.max_body_bytes:
                raise _StorefrontBodyTooLarge()
            return message

        return limited_receive

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        raw_headers = tuple(scope.get("headers", ()))
        method = str(scope.get("method", "")).upper()
        path = str(scope.get("path", ""))
        protected = requires_storefront_gateway(method=method, path=path)
        is_write = method not in {"GET", "HEAD", "OPTIONS"}
        has_storefront_headers, complete = storefront_signing_header_state(
            raw_headers
        )

        async def send_private(message: Message) -> None:
            if message["type"] == "http.response.start":
                message = dict(message)
                message["headers"] = force_private_storefront_response_headers(
                    message.get("headers", ())
                )
            await send(message)

        async def reject(status_code: int, detail: str) -> None:
            response = JSONResponse(
                status_code=status_code,
                content={"detail": detail},
            )
            await response(scope, receive, send_private)

        if not has_storefront_headers:
            if not protected:
                await self.app(scope, receive, send)
                return
            try:
                resolve_allowed_api_hostname(
                    raw_headers=raw_headers,
                    allowed_api_hosts=settings.storefront_context_api_hosts,
                )
            except (TypeError, ValueError):
                await reject(401, "Invalid storefront context")
                return
            if settings.STOREFRONT_CONTEXT_REQUIRE_SIGNED_REQUESTS:
                await reject(401, "Invalid storefront context")
                return
            if not is_write:
                await self.app(scope, receive, send)
                return
            try:
                resolve_idempotency_key_binding(
                    raw_headers=raw_headers,
                    method=method,
                    required_for_write=False,
                )
            except (TypeError, ValueError):
                await reject(400, "Invalid Idempotency-Key")
                return
            try:
                content_length = self._content_length(raw_headers)
            except ValueError:
                await reject(400, "Invalid Content-Length")
                return
            if content_length is not None and content_length > self.max_body_bytes:
                await reject(413, "Storefront request body is too large")
                return
            try:
                await self.app(scope, self._limited_receive(receive), send)
            except _StorefrontBodyTooLarge:
                await reject(413, "Storefront request body is too large")
            return

        if not complete:
            await reject(401, "Invalid storefront context")
            return

        try:
            content_length = self._content_length(raw_headers)
        except ValueError:
            await reject(400, "Invalid Content-Length")
            return
        if content_length is not None and content_length > self.max_body_bytes:
            await reject(413, "Storefront request body is too large")
            return

        body = bytearray()
        digest = sha256()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = bytes(message.get("body", b""))
            if len(body) + len(chunk) > self.max_body_bytes:
                await reject(413, "Storefront request body is too large")
                return
            body.extend(chunk)
            digest.update(chunk)
            if not message.get("more_body", False):
                break

        try:
            verified = authenticate_storefront_envelope(
                raw_headers=raw_headers,
                method=method,
                raw_path=bytes(scope.get("raw_path", b"")),
                query_string=bytes(scope.get("query_string", b"")),
                body_sha256=digest.hexdigest(),
                config=StorefrontEnvelopeAuthConfig(
                    primary_key_id=settings.STOREFRONT_CONTEXT_SIGNING_KEY_ID,
                    primary_secret=settings.STOREFRONT_CONTEXT_SIGNING_SECRET,
                    previous_key_id=(
                        settings.STOREFRONT_CONTEXT_PREVIOUS_SIGNING_KEY_ID
                    ),
                    previous_secret=(
                        settings.STOREFRONT_CONTEXT_PREVIOUS_SIGNING_SECRET
                    ),
                    allowed_api_hosts=settings.storefront_context_api_hosts,
                    max_age_seconds=settings.STOREFRONT_CONTEXT_MAX_AGE_SECONDS,
                ),
            )
        except (TypeError, ValueError):
            await reject(401, "Invalid storefront context")
            return

        scope[STOREFRONT_VERIFIED_ENVELOPE_SCOPE_KEY] = verified
        replayed = False

        async def replay_receive() -> Message:
            nonlocal replayed
            if replayed:
                return {"type": "http.request", "body": b"", "more_body": False}
            replayed = True
            return {
                "type": "http.request",
                "body": bytes(body),
                "more_body": False,
            }

        await self.app(scope, replay_receive, send_private)
