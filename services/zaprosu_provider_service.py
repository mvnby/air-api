"""Bounded Chat Completions transport for the fixed ZAPRO.SU endpoint."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import httpx

BASE_URL = "https://po.zapro.su/v1"
MAX_RESPONSE_BYTES = 256_000
MAX_OUTPUT_TOKENS = 2048
_REQUEST_DEADLINE = 35.0
_IN_FLIGHT = asyncio.Semaphore(4)


class ZaprosuError(ValueError):
    def __init__(self, code: str, *, status: int | None = None, retryable: bool = False):
        self.code = code
        self.status = status
        self.retryable = retryable
        super().__init__(code)


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None


def _error_for_status(status: int, upstream_code: str | None = None) -> ZaprosuError:
    if status in (401, 403):
        return ZaprosuError("authentication_rejected", status=status)
    if status == 429:
        return ZaprosuError("rate_limited", status=status, retryable=True)
    if status == 402:
        return ZaprosuError("balance_unavailable", status=status)
    if upstream_code in {"insufficient_balance", "insufficient_quota"}:
        return ZaprosuError("balance_unavailable", status=status)
    if upstream_code == "get_channel_failed":
        return ZaprosuError("channel_unavailable", status=status)
    if upstream_code in {"model_not_found", "invalid_model"}:
        return ZaprosuError("model_unavailable", status=status)
    if status >= 500:
        return ZaprosuError("upstream_unavailable", status=status, retryable=True)
    return ZaprosuError("model_or_channel_rejected", status=status)


async def _request(method: str, path: str, token: str, payload: dict | None = None) -> dict:
    if not token or len(token) > 4096 or any(ch.isspace() for ch in token):
        raise ZaprosuError("invalid_credential")
    if path not in ("/models", "/chat/completions"):
        raise ZaprosuError("invalid_endpoint")
    try:
        async with asyncio.timeout(_REQUEST_DEADLINE):
            async with _IN_FLIGHT:
                async with httpx.AsyncClient(timeout=30, follow_redirects=False, trust_env=False) as client:
                    request = client.build_request(
                        method, BASE_URL + path,
                        headers={"Authorization": f"Bearer {token}", "Accept": "application/json", "Accept-Encoding": "identity"},
                        json=payload,
                    )
                    response = await client.send(request, stream=True)
                    try:
                        if 300 <= response.status_code < 400:
                            raise ZaprosuError("redirect_rejected", status=response.status_code)
                        if response.status_code >= 400:
                            error_chunks, error_size = [], 0
                            async for chunk in response.aiter_raw():
                                error_size += len(chunk)
                                if error_size > 8192:
                                    break
                                error_chunks.append(chunk)
                            raise _error_for_status(
                                response.status_code,
                                _provider_error_code(b"".join(error_chunks)),
                            )
                        if response.headers.get("content-encoding", "identity").lower() != "identity":
                            raise ZaprosuError("invalid_response")
                        declared = response.headers.get("content-length")
                        if declared and int(declared) > MAX_RESPONSE_BYTES:
                            raise ZaprosuError("response_too_large")
                        chunks, size = [], 0
                        async for chunk in response.aiter_raw():
                            size += len(chunk)
                            if size > MAX_RESPONSE_BYTES:
                                raise ZaprosuError("response_too_large")
                            chunks.append(chunk)
                    finally:
                        await response.aclose()
    except (TimeoutError, httpx.TimeoutException):
        raise ZaprosuError("timeout", retryable=True) from None
    except httpx.TransportError:
        raise ZaprosuError("upstream_unavailable", retryable=True) from None
    except ValueError as exc:
        if isinstance(exc, ZaprosuError):
            raise
        raise ZaprosuError("invalid_response") from None
    try:
        data = json.loads(b"".join(chunks))
    except (ValueError, UnicodeError):
        raise ZaprosuError("invalid_response") from None
    if not isinstance(data, dict):
        raise ZaprosuError("invalid_response")
    if data.get("error"):
        raise _error_for_status(400, _provider_error_code(b"".join(chunks)))
    return data


def _provider_error_code(body: bytes) -> str | None:
    try:
        data = json.loads(body)
    except (UnicodeError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("error"), dict):
        return None
    code = data["error"].get("code")
    return code if isinstance(code, str) else None


async def list_models(token: str) -> list[str]:
    data = await _request("GET", "/models", token)
    rows = data.get("data")
    if not isinstance(rows, list):
        raise ZaprosuError("invalid_response")
    ids = [row.get("id") for row in rows if isinstance(row, dict)]
    return sorted({item for item in ids if isinstance(item, str) and 0 < len(item) <= 160})[:500]


async def chat_completion(
    *, token: str, model: str, prompt: str, system_prompt: str = "",
    max_output_tokens: int = 256,
) -> Completion:
    if not model or len(model) > 160 or any(ch.isspace() for ch in model):
        raise ZaprosuError("invalid_model")
    if not prompt or len(prompt) > 20_000 or len(system_prompt) > 10_000:
        raise ZaprosuError("input_too_large")
    if not 1 <= max_output_tokens <= MAX_OUTPUT_TOKENS:
        raise ZaprosuError("output_limit_exceeded")
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    data = await _request("POST", "/chat/completions", token, {
        "model": model, "messages": messages, "max_tokens": max_output_tokens, "stream": False,
    })
    try:
        content = data["choices"][0]["message"]["content"]
        actual_model = data.get("model") or model
        usage = data.get("usage") or {}
        if not isinstance(content, str) or not isinstance(actual_model, str) or not isinstance(usage, dict):
            raise TypeError
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        if prompt_tokens is not None and (not isinstance(prompt_tokens, int) or prompt_tokens < 0):
            raise TypeError
        if completion_tokens is not None and (not isinstance(completion_tokens, int) or completion_tokens < 0):
            raise TypeError
        return Completion(content, actual_model, prompt_tokens, completion_tokens)
    except (KeyError, IndexError, TypeError):
        raise ZaprosuError("invalid_response") from None
