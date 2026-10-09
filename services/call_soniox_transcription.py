"""Private Files API input and individually addressed async Soniox jobs.

Submission is never retried by this adapter. The pipeline saves submission
intent before POST because client_reference_id is tracking, not idempotency.
"""

import asyncio
import json
import re
from dataclasses import dataclass, field

import httpx

from core.config import settings
from services.call_drive_provider import CallDriveError

ALLOWED_BASE_URLS = frozenset({
    "https://api.soniox.com", "https://api.eu.soniox.com",
    "https://api.jp.soniox.com", "https://api.in.soniox.com",
})
UUID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}")
MODEL = re.compile(r"stt-async-[a-z0-9-]{1,22}")
SOURCE = re.compile(r"[0-9a-f]{64}")
MAX_AUDIO_BYTES = 20 * 1024 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_TRANSCRIPT_LENGTH = 12_000
REQUEST_TIMEOUT_SECONDS = 15.0
METHOD_TIMEOUT_SECONDS = 60.0


def _error(code, *, status_code=502):
    messages = {
        "call_soniox_not_configured": "Распознавание Soniox не настроено",
        "call_soniox_access_denied": "Soniox отклонил доступ к распознаванию",
        "call_soniox_provider_error": "Soniox временно недоступен или вернул неверный ответ",
        "call_soniox_invalid_audio": "Запись не подходит для распознавания Soniox",
        "call_soniox_operation_failed": "Soniox не завершил распознавание записи",
        "call_soniox_submission_uncertain": "Отправка задания Soniox требует ручного разбора",
    }
    return CallDriveError(code, messages[code], status_code=status_code)


@dataclass(frozen=True)
class SonioxConfiguration:
    api_key: str = field(repr=False)
    base_url: str
    model: str


class SonioxCallTranscriptionProvider:
    @staticmethod
    def configuration(*, base_url=None, model=None):
        config = SonioxConfiguration(
            settings.CALL_RECORDINGS_SONIOX_API_KEY.strip(),
            base_url if base_url is not None else settings.CALL_RECORDINGS_SONIOX_API_BASE_URL,
            model if model is not None else settings.CALL_RECORDINGS_SONIOX_MODEL,
        )
        if (not config.api_key or not re.fullmatch(r"[\x21-\x7e]{1,8192}", config.api_key)
                or config.base_url not in ALLOWED_BASE_URLS or not isinstance(config.model, str)
                or not MODEL.fullmatch(config.model) or len(config.model) > 32):
            raise _error("call_soniox_not_configured", status_code=503)
        return config

    @classmethod
    def is_configured(cls):
        try:
            cls.configuration()
            return True
        except CallDriveError:
            return False

    @staticmethod
    def _id(value):
        if not isinstance(value, str) or not UUID.fullmatch(value):
            raise _error("call_soniox_operation_failed", status_code=422)
        return value

    @staticmethod
    def _client(config):
        return httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=False, trust_env=False,
                                 headers={"Authorization": f"Bearer {config.api_key}"})

    @staticmethod
    async def _json(client, method, url, *, creating=False, **kwargs):
        async with client.stream(method, url, **kwargs) as response:
            status = response.status_code
            if status in {401, 403}:
                raise _error("call_soniox_access_denied", status_code=403)
            if status in {400, 413, 415, 422}:
                raise _error("call_soniox_invalid_audio", status_code=422)
            if status == 404:
                raise _error("call_soniox_operation_failed", status_code=422)
            if status != (201 if method == "POST" else 200):
                code = "call_soniox_submission_uncertain" if creating and (status >= 500 or status < 400) else "call_soniox_provider_error"
                raise _error(code)
            chunks, size = [], 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise _error("call_soniox_submission_uncertain" if creating else "call_soniox_provider_error")
                chunks.append(chunk)
        try:
            data = json.loads(b"".join(chunks))
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except (ValueError, UnicodeError):
            raise _error("call_soniox_submission_uncertain" if creating else "call_soniox_provider_error") from None

    @classmethod
    async def upload(cls, *, content, source_id, base_url, model):
        if (not isinstance(content, bytes) or not 12 <= len(content) <= MAX_AUDIO_BYTES
                or content[:4] != b"RIFF" or content[8:12] != b"WAVE"
                or not isinstance(source_id, str) or not SOURCE.fullmatch(source_id)):
            raise _error("call_soniox_invalid_audio", status_code=422)
        config = cls.configuration(base_url=base_url, model=model)
        try:
            async with asyncio.timeout(METHOD_TIMEOUT_SECONDS):
                async with cls._client(config) as client:
                    data = await cls._json(client, "POST", f"{config.base_url}/v1/files",
                                           files={"file": (f"{source_id}.wav", content, "audio/wav")})
        except (TimeoutError, httpx.RequestError):
            raise _error("call_soniox_provider_error") from None
        return cls._id(data.get("id"))

    @classmethod
    async def submit(cls, *, file_id, source_id, base_url, model):
        cls._id(file_id)
        if not isinstance(source_id, str) or not SOURCE.fullmatch(source_id):
            raise _error("call_soniox_invalid_audio", status_code=422)
        config = cls.configuration(base_url=base_url, model=model)
        try:
            async with asyncio.timeout(METHOD_TIMEOUT_SECONDS):
                async with cls._client(config) as client:
                    data = await cls._json(client, "POST", f"{config.base_url}/v1/transcriptions", creating=True, json={
                        "file_id": file_id, "model": config.model, "language_hints": ["ru"],
                        "client_reference_id": source_id,
                    })
        except (TimeoutError, httpx.RequestError):
            raise _error("call_soniox_submission_uncertain") from None
        if (not isinstance(data.get("id"), str) or not UUID.fullmatch(data["id"])
                or data.get("file_id") != file_id or data.get("model") != config.model
                or data.get("status") not in {"queued", "processing", "completed", "error"}):
            raise _error("call_soniox_submission_uncertain")
        return data["id"]

    @classmethod
    async def poll(cls, *, operation_name, file_id, base_url, model):
        cls._id(operation_name)
        cls._id(file_id)
        config = cls.configuration(base_url=base_url, model=model)
        try:
            async with asyncio.timeout(METHOD_TIMEOUT_SECONDS):
                async with cls._client(config) as client:
                    url = f"{config.base_url}/v1/transcriptions/{operation_name}"
                    data = await cls._json(client, "GET", url)
                    if (data.get("id") != operation_name or data.get("file_id") != file_id
                            or data.get("model") != model):
                        raise _error("call_soniox_provider_error")
                    if data.get("status") in {"queued", "processing"}:
                        return None
                    if data.get("status") == "error":
                        raise _error("call_soniox_operation_failed", status_code=422)
                    if data.get("status") != "completed":
                        raise _error("call_soniox_provider_error")
                    transcript = await cls._json(client, "GET", f"{url}/transcript")
        except (TimeoutError, httpx.RequestError):
            raise _error("call_soniox_provider_error") from None
        if transcript.get("id") != operation_name or not isinstance(transcript.get("text"), str):
            raise _error("call_soniox_provider_error")
        text = " ".join(transcript["text"].split())
        if not text:
            raise _error("call_soniox_invalid_audio", status_code=422)
        if len(text) > MAX_TRANSCRIPT_LENGTH:
            raise _error("call_soniox_provider_error")
        return text

    @classmethod
    async def cleanup(cls, *, operation_name, file_id, base_url, model):
        """Delete only the caller's IDs, and preserve input of a running job."""
        try:
            cls._id(operation_name)
            cls._id(file_id)
            config = cls.configuration(base_url=base_url, model=model)
            async with asyncio.timeout(METHOD_TIMEOUT_SECONDS):
                async with cls._client(config) as client:
                    url = f"{config.base_url}/v1/transcriptions/{operation_name}"
                    async with client.stream("GET", url) as response:
                        if response.status_code == 404:
                            data = None  # A prior cleanup may have already deleted the job.
                        elif response.status_code == 200:
                            chunks, size = [], 0
                            async for chunk in response.aiter_bytes():
                                size += len(chunk)
                                if size > MAX_RESPONSE_BYTES:
                                    return False
                                chunks.append(chunk)
                            data = json.loads(b"".join(chunks))
                        else:
                            return False
                    if data is not None:
                        if (not isinstance(data, dict) or data.get("id") != operation_name
                                or data.get("file_id") != file_id or data.get("model") != model
                                or data.get("status") not in {"completed", "error"}):
                            return False
                        async with client.stream("DELETE", url) as response:
                            if response.status_code not in {200, 204, 404}:
                                return False
                    async with client.stream("DELETE", f"{config.base_url}/v1/files/{file_id}") as response:
                        return response.status_code in {200, 204, 404}
        except Exception:
            return False
