"""Bounded OpenAI transport for extracting candidate citations from tender text."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence

import httpx

from core.config import settings


_OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
_SUPPORTED_MODELS = frozenset({"gpt-5.4-mini", "gpt-5.4-mini-2026-03-17"})
_MAX_REQUEST_BYTES = 2_000_000
_MAX_RESPONSE_BYTES = 512_000
_MAX_OUTPUT_TOKENS = 8_192
_REQUEST_TIMEOUT_SECONDS = 45.0


class OpenAITenderProviderError(ValueError):
    """Stable provider error with no credentials or tender text in the message."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"OpenAI tender extraction failed ({code})")


def _response_format(fact_kinds: Sequence[str]) -> dict:
    return {
        "type": "json_schema",
        "name": "tender_fact_candidates",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["facts"],
            "properties": {
                "facts": {
                    "type": "array",
                    "maxItems": 80,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["kind", "fragment", "quote"],
                        "properties": {
                            "kind": {"type": "string", "enum": list(fact_kinds)},
                            "fragment": {"type": "integer", "minimum": 0, "maximum": 511},
                            "quote": {"type": "string", "pattern": r"^[\s\S]{1,1000}$"},
                        },
                    },
                },
            },
        },
    }


async def _read_response(response: httpx.Response) -> bytearray:
    status = response.status_code
    if status != 200:
        if status in {401, 403}:
            raise OpenAITenderProviderError("authentication_rejected")
        if status == 429:
            raise OpenAITenderProviderError("rate_limited")
        raise OpenAITenderProviderError("upstream_error")
    if response.headers.get("content-encoding", "identity").lower() != "identity":
        raise OpenAITenderProviderError("unexpected_encoding")
    body = bytearray()
    async for chunk in response.aiter_bytes(chunk_size=16_384):
        if len(body) + len(chunk) > _MAX_RESPONSE_BYTES:
            raise OpenAITenderProviderError("response_too_large")
        body.extend(chunk)
    return body


def _parse_response(body: bytearray) -> tuple[str, str]:
    try:
        response = json.loads(body)
        if response["status"] == "incomplete":
            raise OpenAITenderProviderError("incomplete")
        if response["status"] != "completed" or response["model"] not in _SUPPORTED_MODELS:
            raise OpenAITenderProviderError("invalid_response")

        messages = [item for item in response["output"] if item["type"] != "reasoning"]
        message, = messages
        if message["type"] != "message" or message["role"] != "assistant" or message["status"] != "completed":
            raise OpenAITenderProviderError("invalid_response")
        content, = message["content"]
        if content["type"] == "refusal":
            raise OpenAITenderProviderError("refused")
        if content["type"] != "output_text" or not isinstance(content["text"], str):
            raise OpenAITenderProviderError("invalid_response")
        return content["text"], response["model"]
    except OpenAITenderProviderError:
        raise
    except (KeyError, TypeError, ValueError, RecursionError):
        raise OpenAITenderProviderError("invalid_response") from None


async def request_openai_tender_completion(
    *,
    prompt: str,
    system_prompt: str,
    fact_kinds: Sequence[str],
) -> tuple[str, str]:
    """Return candidate JSON and the responding model for local evidence validation."""
    key = settings.OPENAI_API_KEY.strip()
    if not key:
        raise OpenAITenderProviderError("not_configured")
    if not key.isascii() or any(not 33 <= ord(char) <= 126 for char in key):
        raise OpenAITenderProviderError("invalid_credential")
    model = settings.TENDER_OPENAI_MODEL
    if model not in _SUPPORTED_MODELS:
        raise OpenAITenderProviderError("unsupported_model")
    if len(prompt) + len(system_prompt) > _MAX_REQUEST_BYTES:
        raise OpenAITenderProviderError("request_too_large")
    payload = json.dumps({
        "model": model,
        "store": False,
        "tools": [],
        "reasoning": {"effort": "none"},
        "max_output_tokens": _MAX_OUTPUT_TOKENS,
        "instructions": system_prompt,
        "input": prompt,
        "text": {"format": _response_format(fact_kinds)},
    }, ensure_ascii=False).encode("utf-8")
    if len(payload) > _MAX_REQUEST_BYTES:
        raise OpenAITenderProviderError("request_too_large")

    try:
        async with asyncio.timeout(_REQUEST_TIMEOUT_SECONDS):
            async with httpx.AsyncClient(
                timeout=_REQUEST_TIMEOUT_SECONDS, trust_env=False, follow_redirects=False,
            ) as client:
                async with client.stream(
                    "POST",
                    _OPENAI_RESPONSES_URL,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                    },
                    content=payload,
                ) as response:
                    return _parse_response(await _read_response(response))
    except (TimeoutError, httpx.TimeoutException):
        raise OpenAITenderProviderError("timeout") from None
    except httpx.HTTPError:
        raise OpenAITenderProviderError("unavailable") from None
