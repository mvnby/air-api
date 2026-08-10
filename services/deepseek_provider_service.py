"""Shared typed DeepSeek transport used by repair automation."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from core.config import settings


MAX_DEEPSEEK_RESPONSE_BYTES = 512_000
MAX_DEEPSEEK_OUTPUT_TOKENS = 4_096
DEEPSEEK_REQUEST_DEADLINE_SECONDS = 50.0


class DefectActAIProviderError(ValueError):
    """DeepSeek failure with an explicit retry contract."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None,
        retryable: bool,
        code: str,
    ) -> None:
        self.status = status
        self.retryable = bool(retryable)
        self.code = str(code)[:100]
        super().__init__(str(message)[:500])


async def request_deepseek_completion(
    *,
    prompt: str,
    system_prompt: str,
    temperature: float,
    thinking_enabled: bool | None = None,
) -> str:
    token = settings.DEEPSEEK_TOKEN.strip()
    if not token:
        raise DefectActAIProviderError(
            "DEEPSEEK_TOKEN is not configured",
            status=None,
            retryable=False,
            code="not_configured",
        )

    request_payload: dict[str, Any] = {
        "model": settings.DEEPSEEK_MODEL,
        "temperature": temperature,
        "max_tokens": MAX_DEEPSEEK_OUTPUT_TOKENS,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
    }
    if thinking_enabled is not None:
        request_payload["thinking"] = {
            "type": "enabled" if thinking_enabled else "disabled"
        }

    response: httpx.Response | None = None
    try:
        async with asyncio.timeout(DEEPSEEK_REQUEST_DEADLINE_SECONDS):
            async with httpx.AsyncClient(timeout=45.0, trust_env=False) as client:
                request = client.build_request(
                    "POST",
                    settings.DEEPSEEK_API_URL,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                    },
                    json=request_payload,
                )
                response = await client.send(request, stream=True)
                try:
                    raw_response = await _read_limited_response(response)
                finally:
                    await response.aclose()
    except (TimeoutError, httpx.TimeoutException) as exc:
        raise DefectActAIProviderError(
            "DeepSeek request timed out",
            status=None,
            retryable=True,
            code="timeout",
        ) from exc
    except httpx.TransportError as exc:
        raise DefectActAIProviderError(
            "DeepSeek is temporarily unavailable",
            status=None,
            retryable=True,
            code="unavailable",
        ) from exc

    assert response is not None
    if response.status_code >= 400:
        status = int(response.status_code)
        code, retryable = _status_contract(status)
        raise DefectActAIProviderError(
            f"DeepSeek returned HTTP {status}: {_error_message(raw_response)}",
            status=status,
            retryable=retryable,
            code=code,
        )
    try:
        data = json.loads(raw_response)
        return str(data["choices"][0]["message"]["content"])
    except ValueError as exc:
        raise invalid_deepseek_response(
            "DeepSeek returned invalid JSON",
            status=int(response.status_code),
        ) from exc
    except (KeyError, IndexError, TypeError) as exc:
        raise invalid_deepseek_response(
            "DeepSeek response has unexpected format",
            status=int(response.status_code),
        ) from exc


def invalid_deepseek_response(
    message: str,
    *,
    status: int | None = 200,
) -> DefectActAIProviderError:
    return DefectActAIProviderError(
        message,
        status=status,
        retryable=True,
        code="invalid_response",
    )


def _status_contract(status: int) -> tuple[str, bool]:
    if status in {401, 403}:
        return "authentication_rejected", False
    if status == 429:
        return "rate_limited", True
    if status >= 500:
        return "upstream_error", True
    return "request_rejected", False


async def _read_limited_response(response: httpx.Response) -> bytes:
    content_encoding = response.headers.get("content-encoding", "").strip().lower()
    if content_encoding not in {"", "identity"}:
        raise invalid_deepseek_response(
            "DeepSeek returned unsupported content encoding",
            status=int(response.status_code),
        )
    declared_size = response.headers.get("content-length")
    if declared_size:
        try:
            if int(declared_size) > MAX_DEEPSEEK_RESPONSE_BYTES:
                raise invalid_deepseek_response(
                    "DeepSeek response is too large",
                    status=int(response.status_code),
                )
        except ValueError:
            pass
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.aiter_raw():
        size += len(chunk)
        if size > MAX_DEEPSEEK_RESPONSE_BYTES:
            raise invalid_deepseek_response(
                "DeepSeek response is too large",
                status=int(response.status_code),
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _error_message(raw_response: bytes) -> str:
    try:
        data: Any = json.loads(raw_response)
    except (UnicodeDecodeError, ValueError):
        return raw_response.decode("utf-8", errors="replace")[:300]
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        message = str(error.get("message") or "").strip()
        if message:
            return message[:300]
    return str(data)[:300]
