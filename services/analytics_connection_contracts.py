from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from core.config import settings
from core.integration_credential_keyring import (
    DecryptedIntegrationCredential,
    IntegrationCredentialUnavailable,
    IntegrationCredentialUnreadable,
    InvalidIntegrationCredentialKeyring,
)


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
    """Storefront-bound analytics credentials with transitional legacy reads."""

    _ENCRYPTION_CONTEXT = b"mvn.analytics.credentials.fernet.v1"
    _FINGERPRINT_CONTEXT = b"mvn.analytics.credentials.fingerprint.v1"

    @classmethod
    def encrypt(
        cls,
        payload: dict[str, Any],
        *,
        tenant_id: int,
        storefront_id: int,
        provider: str,
    ) -> str:
        keyring = settings.integration_credential_keyring
        if keyring.enabled and keyring.write_mode == "active":
            value: dict[str, Any] = {
                "version": 1,
                "tenant_id": int(tenant_id),
                "storefront_id": int(storefront_id),
                "provider": str(provider),
                "credentials": payload,
            }
        else:
            value = payload
        raw = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            if keyring.enabled and keyring.write_mode == "active":
                return keyring.encrypt(raw, context=cls._ENCRYPTION_CONTEXT)
            return keyring.encrypt_legacy(
                raw,
                context=cls._ENCRYPTION_CONTEXT,
                local_legacy_secret=str(settings.SECRET_KEY or ""),
            )
        except (IntegrationCredentialUnavailable, InvalidIntegrationCredentialKeyring) as exc:
            raise cls._unavailable() from exc

    @classmethod
    def decrypt(
        cls,
        encrypted: str,
        *,
        tenant_id: int,
        storefront_id: int,
        provider: str,
    ) -> dict[str, Any]:
        payload, _ = cls.decrypt_with_source(
            encrypted,
            tenant_id=tenant_id,
            storefront_id=storefront_id,
            provider=provider,
        )
        return payload

    @classmethod
    def decrypt_with_source(
        cls,
        encrypted: str,
        *,
        tenant_id: int,
        storefront_id: int,
        provider: str,
    ) -> tuple[dict[str, Any], DecryptedIntegrationCredential]:
        try:
            decrypted = settings.integration_credential_keyring.decrypt(
                encrypted,
                context=cls._ENCRYPTION_CONTEXT,
                local_legacy_secret=str(settings.SECRET_KEY or ""),
            )
            decoded = json.loads(decrypted.plaintext)
        except IntegrationCredentialUnavailable as exc:
            raise cls._unavailable() from exc
        except (
            IntegrationCredentialUnreadable,
            InvalidIntegrationCredentialKeyring,
            UnicodeError,
            ValueError,
            TypeError,
            json.JSONDecodeError,
        ) as exc:
            raise cls._unreadable() from exc
        if decrypted.source == "legacy":
            payload = decoded
        elif (
            isinstance(decoded, dict)
            and decoded.get("version") == 1
            and decoded.get("tenant_id") == int(tenant_id)
            and decoded.get("storefront_id") == int(storefront_id)
            and decoded.get("provider") == str(provider)
        ):
            payload = decoded.get("credentials")
        else:
            raise cls._unreadable()
        if not isinstance(payload, dict) or not all(
            isinstance(key, str) for key in payload
        ):
            raise cls._unreadable()
        return payload, decrypted

    @classmethod
    def fingerprint(cls, secret_value: str) -> str:
        keyring = settings.integration_credential_keyring
        try:
            if keyring.enabled and keyring.write_mode == "active":
                return keyring.fingerprint(
                    secret_value.encode("utf-8"),
                    context=cls._FINGERPRINT_CONTEXT,
                )
            return keyring.fingerprint_legacy(
                secret_value.encode("utf-8"),
                context=cls._FINGERPRINT_CONTEXT,
                local_legacy_secret=str(settings.SECRET_KEY or ""),
            )
        except (IntegrationCredentialUnavailable, InvalidIntegrationCredentialKeyring) as exc:
            raise cls._unavailable() from exc

    @staticmethod
    def _unavailable() -> AnalyticsConnectionError:
        return AnalyticsConnectionError(
            "credential_encryption_unavailable",
            "Хранилище секретов временно недоступно",
            status_code=503,
        )

    @staticmethod
    def _unreadable() -> AnalyticsConnectionError:
        return AnalyticsConnectionError(
            "credentials_unreadable",
            "Подключение сохранено, но сервер не может прочитать его настройки",
            status_code=503,
        )


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
    error_code: str | None = None


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
