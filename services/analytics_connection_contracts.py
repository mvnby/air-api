from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from core.config import settings


YANDEX_METRIKA = "yandex_metrika"
YANDEX_DIRECT = "yandex_direct"
YANDEX_WEBMASTER = "yandex_webmaster"
GOOGLE_ANALYTICS = "google_analytics"
GOOGLE_ADS = "google_ads"
GOOGLE_SEARCH_CONSOLE = "google_search_console"


class AnalyticsConnectionError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class AnalyticsCredentialCipher:
    """Authenticated encryption with a domain-separated key derived from SECRET_KEY."""

    _ENCRYPTION_CONTEXT = b"mvn.analytics.credentials.fernet.v1"
    _FINGERPRINT_CONTEXT = b"mvn.analytics.credentials.fingerprint.v1"

    @classmethod
    def _fernet(cls) -> Fernet:
        secret = str(settings.SECRET_KEY or "").encode("utf-8")
        if len(secret) < 16:
            raise AnalyticsConnectionError(
                "credential_encryption_unavailable",
                "Хранилище секретов временно недоступно",
                status_code=503,
            )
        key = hmac.new(secret, cls._ENCRYPTION_CONTEXT, hashlib.sha256).digest()
        return Fernet(base64.urlsafe_b64encode(key))

    @classmethod
    def encrypt(cls, payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        return cls._fernet().encrypt(raw).decode("ascii")

    @classmethod
    def decrypt(cls, encrypted: str) -> dict[str, Any]:
        try:
            raw = cls._fernet().decrypt(encrypted.encode("ascii"))
            payload = json.loads(raw)
        except (InvalidToken, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise AnalyticsConnectionError(
                "credentials_unreadable",
                "Сохранённое подключение нужно настроить заново",
                status_code=503,
            ) from exc
        if not isinstance(payload, dict) or not all(
            isinstance(key, str) for key in payload
        ):
            raise AnalyticsConnectionError(
                "credentials_unreadable",
                "Сохранённое подключение нужно настроить заново",
                status_code=503,
            )
        return payload

    @classmethod
    def fingerprint(cls, secret_value: str) -> str:
        key = str(settings.SECRET_KEY or "").encode("utf-8")
        return hmac.new(
            key,
            cls._FINGERPRINT_CONTEXT + secret_value.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()


@dataclass(frozen=True)
class AnalyticsRuntimeCredentials:
    counter_id: str
    oauth_token: str
    fingerprint: str


@dataclass(frozen=True)
class AnalyticsRuntimeConnection:
    provider: str
    public_config: dict[str, str]
    credentials: dict[str, Any]
    fingerprint: str


PROVIDER_DEFINITIONS = (
    (
        YANDEX_METRIKA,
        "Яндекс Метрика",
        "Посещения сайта, источники трафика и воронка до заявки.",
        True,
    ),
    (
        YANDEX_DIRECT,
        "Яндекс Директ",
        "Расходы, показы, клики, CTR и стоимость заявки.",
        True,
    ),
    (
        YANDEX_WEBMASTER,
        "Яндекс Вебмастер",
        "Поисковые запросы, показы, клики и позиции в Яндексе.",
        True,
    ),
    (
        GOOGLE_ANALYTICS,
        "Google Analytics 4",
        "Трафик и поведение посетителей из GA4.",
        True,
    ),
    (
        GOOGLE_ADS,
        "Google Ads",
        "Расходы и эффективность рекламных кампаний Google.",
        True,
    ),
    (
        GOOGLE_SEARCH_CONSOLE,
        "Google Search Console",
        "Поисковые запросы, CTR и позиции сайта в Google.",
        True,
    ),
)
