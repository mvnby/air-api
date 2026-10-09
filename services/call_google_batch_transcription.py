"""One private WAV per Google Speech v2 dynamic batch operation.

The caller persists the returned operation before polling. This adapter never
retries a submission and never fetches a destination supplied by Google output.
"""

import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import httpx
import requests
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from core.config import settings
from services.call_drive_provider import CallDriveError

CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
TOKEN_URL = "https://oauth2.googleapis.com/token"
MAX_AUDIO_BYTES = 20 * 1024 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_TRANSCRIPT_LENGTH = 12_000
METHOD_TIMEOUT_SECONDS = 60.0
REQUEST_TIMEOUT_SECONDS = 15.0
SOURCE_ID = re.compile(r"[0-9a-f]{64}")
PROJECT_ID = re.compile(r"(?:[a-z][a-z0-9-]{4,28}[a-z0-9]|[0-9]{6,20})")
BUCKET_NAME = re.compile(r"[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]")
MODEL_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}")


def _error(code: str, *, status_code: int = 502) -> CallDriveError:
    messages = {
        "call_google_not_configured": "Пакетное распознавание Google не настроено",
        "call_google_access_denied": "Google отклонил доступ к пакетному распознаванию",
        "call_google_provider_error": "Пакетное распознавание Google временно недоступно или вернуло неверный ответ",
        "call_google_invalid_audio": "Запись не подходит для пакетного распознавания Google",
        "call_google_operation_failed": "Google не завершил пакетное распознавание записи",
    }
    return CallDriveError(code, messages[code], status_code=status_code)


@dataclass(frozen=True)
class _Configuration:
    credentials_file: str
    project: str
    bucket: str
    location: str
    model: str

    @property
    def speech_url(self) -> str:
        return f"https://{self.location}-speech.googleapis.com/v2"

    def object_name(self, source_id: str) -> str:
        return f"call-recordings/{source_id}.wav"

    def audio_uri(self, source_id: str) -> str:
        return f"gs://{self.bucket}/{self.object_name(source_id)}"

    def valid_operation(self, value) -> bool:
        prefix = f"projects/{self.project}/locations/{self.location}/operations/"
        return isinstance(value, str) and bool(re.fullmatch(re.escape(prefix) + r"[A-Za-z0-9_-]{1,128}", value))


class _TokenSession(requests.Session):
    """Google-auth's transport has a larger default timeout and follows redirects."""

    def __init__(self):
        super().__init__()
        self.trust_env = False

    def request(self, method, url, **kwargs):
        if url != TOKEN_URL:
            raise ValueError("Unsupported Google authentication endpoint")
        kwargs["timeout"] = REQUEST_TIMEOUT_SECONDS
        kwargs["allow_redirects"] = False
        return super().request(method, url, **kwargs)


class GoogleCallBatchTranscriptionProvider:
    @staticmethod
    def _configuration() -> _Configuration:
        config = _Configuration(
            str(getattr(settings, "CALL_RECORDINGS_GOOGLE_CREDENTIALS_FILE", "") or "").strip(),
            str(getattr(settings, "CALL_RECORDINGS_GOOGLE_PROJECT_ID", "") or "").strip(),
            str(getattr(settings, "CALL_RECORDINGS_GOOGLE_BUCKET", "") or "").strip(),
            str(getattr(settings, "CALL_RECORDINGS_GOOGLE_LOCATION", "eu") or "").strip(),
            str(getattr(settings, "CALL_RECORDINGS_GOOGLE_MODEL", "chirp_3") or "").strip(),
        )
        if (not config.credentials_file or not PROJECT_ID.fullmatch(config.project)
                or not BUCKET_NAME.fullmatch(config.bucket) or ".." in config.bucket
                or config.location not in {"eu", "us"} or not MODEL_NAME.fullmatch(config.model)):
            raise _error("call_google_not_configured", status_code=503)
        return config

    @staticmethod
    def _credential_info(config: _Configuration) -> dict:
        try:
            path = Path(config.credentials_file)
            if not path.is_file():
                raise ValueError("Unavailable credential file")
            with path.open("rb") as stream:
                content = stream.read(64 * 1024 + 1)
            if len(content) > 64 * 1024:
                raise ValueError("Unsupported credential size")
            info = json.loads(content)
            if (not isinstance(info, dict) or info.get("type") != "service_account"
                    or info.get("token_uri") != TOKEN_URL
                    or info.get("universe_domain", "googleapis.com") != "googleapis.com"
                    or not isinstance(info.get("client_email"), str) or not info["client_email"]
                    or not isinstance(info.get("private_key"), str) or not info["private_key"]):
                raise ValueError("Unsupported service account")
            return info
        except Exception:
            raise _error("call_google_not_configured", status_code=503) from None

    @classmethod
    def is_configured(cls) -> bool:
        try:
            cls._credential_info(cls._configuration())
            return True
        except CallDriveError:
            return False

    @classmethod
    def _refresh_token(cls, config: _Configuration) -> str:
        info = cls._credential_info(config)
        try:
            credentials = service_account.Credentials.from_service_account_info(info, scopes=(CLOUD_PLATFORM_SCOPE,))
        except Exception:
            raise _error("call_google_not_configured", status_code=503) from None
        try:
            with _TokenSession() as session:
                credentials.refresh(Request(session=session))
        except RefreshError as exc:
            code = "call_google_provider_error" if exc.retryable else "call_google_access_denied"
            raise _error(code, status_code=502 if exc.retryable else 403) from None
        except Exception:
            raise _error("call_google_provider_error") from None
        if not isinstance(credentials.token, str) or not re.fullmatch(r"[A-Za-z0-9._~+/-]{1,8192}", credentials.token):
            raise _error("call_google_provider_error")
        return credentials.token

    @classmethod
    async def _access_token(cls, config: _Configuration) -> str:
        return await asyncio.to_thread(cls._refresh_token, config)

    @staticmethod
    def _source(source_id: str) -> None:
        if not isinstance(source_id, str) or not SOURCE_ID.fullmatch(source_id):
            raise _error("call_google_invalid_audio", status_code=422)

    @staticmethod
    def _status(response: httpx.Response) -> None:
        if response.status_code in {401, 403}:
            raise _error("call_google_access_denied", status_code=403)
        if response.status_code in {413, 415, 422}:
            raise _error("call_google_invalid_audio", status_code=422)
        if response.status_code != 200:
            raise _error("call_google_provider_error")

    @classmethod
    async def _json(cls, client, method: str, url: str, **kwargs) -> dict:
        async with client.stream(method, url, **kwargs) as response:
            cls._status(response)
            chunks, size = [], 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise _error("call_google_provider_error")
                chunks.append(chunk)
        try:
            data = json.loads(b"".join(chunks))
        except (ValueError, UnicodeError):
            raise _error("call_google_provider_error") from None
        if not isinstance(data, dict):
            raise _error("call_google_provider_error")
        return data

    @classmethod
    async def submit(cls, *, content: bytes, source_id: str) -> str:
        cls._source(source_id)
        if (not isinstance(content, bytes) or not 12 <= len(content) <= MAX_AUDIO_BYTES
                or content[:4] != b"RIFF" or content[8:12] != b"WAVE"):
            raise _error("call_google_invalid_audio", status_code=422)
        config = cls._configuration()
        try:
            async with asyncio.timeout(METHOD_TIMEOUT_SECONDS):
                token = await cls._access_token(config)
                async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=False, trust_env=False, headers={"Authorization": f"Bearer {token}"}) as client:
                    async with client.stream("POST", f"https://storage.googleapis.com/upload/storage/v1/b/{config.bucket}/o", params={"uploadType": "media", "name": config.object_name(source_id), "ifGenerationMatch": "0"}, content=content, headers={"Content-Type": "audio/wav"}) as response:
                        if response.status_code not in {200, 201, 412}:
                            cls._status(response)
                    data = await cls._json(client, "POST", f"{config.speech_url}/projects/{config.project}/locations/{config.location}/recognizers/_:batchRecognize", json={
                        "config": {"autoDecodingConfig": {}, "languageCodes": ["ru-RU"], "model": config.model},
                        "files": [{"uri": config.audio_uri(source_id)}],
                        "recognitionOutputConfig": {"inlineResponseConfig": {}},
                        "processingStrategy": "DYNAMIC_BATCHING",
                    })
        except (TimeoutError, httpx.RequestError):
            raise _error("call_google_provider_error") from None
        if not config.valid_operation(data.get("name")):
            raise _error("call_google_provider_error")
        return data["name"]

    @classmethod
    async def poll(cls, *, operation_name: str, source_id: str) -> str | None:
        cls._source(source_id)
        config = cls._configuration()
        if not config.valid_operation(operation_name):
            raise _error("call_google_operation_failed", status_code=422)
        try:
            async with asyncio.timeout(METHOD_TIMEOUT_SECONDS):
                token = await cls._access_token(config)
                async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=False, trust_env=False, headers={"Authorization": f"Bearer {token}"}) as client:
                    data = await cls._json(client, "GET", f"{config.speech_url}/{operation_name}")
        except (TimeoutError, httpx.RequestError):
            raise _error("call_google_provider_error") from None
        if data.get("name") != operation_name or not isinstance(data.get("done", False), bool):
            raise _error("call_google_provider_error")
        if "error" in data:
            raise _error("call_google_operation_failed", status_code=422)
        if not data.get("done", False):
            if "response" in data:
                raise _error("call_google_provider_error")
            return None
        try:
            results = data["response"]["results"]
            if not isinstance(results, dict) or set(results) != {config.audio_uri(source_id)}:
                raise ValueError("Unexpected file result")
            file_result = results[config.audio_uri(source_id)]
            if not isinstance(file_result, dict):
                raise ValueError("Unexpected file result")
            if "error" in file_result:
                raise _error("call_google_operation_failed", status_code=422)
            segments = file_result["inlineResult"]["transcript"]["results"]
            if not isinstance(segments, list):
                raise ValueError("Unexpected transcript")
            parts = []
            for segment in segments:
                text = segment["alternatives"][0]["transcript"]
                if not isinstance(text, str):
                    raise ValueError("Unexpected transcript")
                parts.append(" ".join(text.split()))
            transcript = " ".join(part for part in parts if part)
        except CallDriveError:
            raise
        except (KeyError, TypeError, ValueError, IndexError):
            raise _error("call_google_provider_error") from None
        if not transcript:
            raise _error("call_google_invalid_audio", status_code=422)
        if len(transcript) > MAX_TRANSCRIPT_LENGTH:
            raise _error("call_google_provider_error")
        return transcript

    @classmethod
    async def delete_audio(cls, *, source_id: str) -> bool:
        try:
            cls._source(source_id)
            config = cls._configuration()
            async with asyncio.timeout(METHOD_TIMEOUT_SECONDS):
                token = await cls._access_token(config)
                async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=False, trust_env=False, headers={"Authorization": f"Bearer {token}"}) as client:
                    async with client.stream("DELETE", f"https://storage.googleapis.com/storage/v1/b/{config.bucket}/o/{quote(config.object_name(source_id), safe='')}") as response:
                        return response.status_code in {200, 204, 404}
        except Exception:
            return False
