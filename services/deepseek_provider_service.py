"""Shared typed DeepSeek transport used by repair automation."""

from __future__ import annotations

from typing import Any

import httpx

from core.config import settings


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
) -> str:
    token = settings.DEEPSEEK_TOKEN.strip()
    if not token:
        raise DefectActAIProviderError(
            "DEEPSEEK_TOKEN is not configured",
            status=None,
            retryable=False,
            code="not_configured",
        )

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                settings.DEEPSEEK_API_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.DEEPSEEK_MODEL,
                    "temperature": temperature,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
    except httpx.TimeoutException as exc:
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

    if response.status_code >= 400:
        status = int(response.status_code)
        code, retryable = _status_contract(status)
        raise DefectActAIProviderError(
            f"DeepSeek returned HTTP {status}: {_error_message(response)}",
            status=status,
            retryable=retryable,
            code=code,
        )
    try:
        data = response.json()
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


def _error_message(response: httpx.Response) -> str:
    try:
        data: Any = response.json()
    except ValueError:
        return response.text[:300]
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        message = str(error.get("message") or "").strip()
        if message:
            return message[:300]
    return str(data)[:300]
