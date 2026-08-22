from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from core.request_context import current_request_id
from models import AnalyticsConnection, TenantAuditEvent
from models.tenancy import TenantScope
from schemas_analytics import AnalyticsConnectionItem


YANDEX_METRIKA = "yandex_metrika"


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
    def encrypt(cls, payload: dict[str, str]) -> str:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        return cls._fernet().encrypt(raw).decode("ascii")

    @classmethod
    def decrypt(cls, encrypted: str) -> dict[str, str]:
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
            isinstance(key, str) and isinstance(value, str)
            for key, value in payload.items()
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


_PROVIDER_DEFINITIONS = (
    (
        YANDEX_METRIKA,
        "Яндекс Метрика",
        "Посещения сайта, источники трафика и воронка до заявки.",
        True,
    ),
    (
        "yandex_direct",
        "Яндекс Директ",
        "Расходы, показы, клики, CTR и стоимость заявки.",
        False,
    ),
    (
        "google_analytics",
        "Google Analytics 4",
        "Трафик и поведение посетителей из GA4.",
        False,
    ),
    (
        "google_ads",
        "Google Ads",
        "Расходы и эффективность рекламных кампаний Google.",
        False,
    ),
)


class AnalyticsConnectionService:
    METRIKA_COUNTER_URL = "https://api-metrika.yandex.net/management/v1/counter/{counter_id}"

    def __init__(
        self,
        *,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
    ) -> None:
        self._client_factory = client_factory or (
            lambda: httpx.AsyncClient(
                timeout=max(0.1, settings.DASHBOARD_METRIKA_TIMEOUT_SECONDS),
                trust_env=False,
            )
        )

    @staticmethod
    async def _get_connection(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        provider: str,
        for_update: bool = False,
    ) -> AnalyticsConnection | None:
        statement = select(AnalyticsConnection).where(
            AnalyticsConnection.tenant_id == tenant_scope.tenant_id,
            AnalyticsConnection.storefront_id == tenant_scope.storefront_id,
            AnalyticsConnection.provider == provider,
        )
        if for_update:
            statement = statement.with_for_update()
        return (await session.execute(statement)).scalar_one_or_none()

    @classmethod
    async def list_connections(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> list[AnalyticsConnectionItem]:
        rows = (
            await session.execute(
                select(AnalyticsConnection).where(
                    AnalyticsConnection.tenant_id == tenant_scope.tenant_id,
                    AnalyticsConnection.storefront_id == tenant_scope.storefront_id,
                )
            )
        ).scalars().all()
        by_provider = {row.provider: row for row in rows}
        items: list[AnalyticsConnectionItem] = []
        for provider, label, description, available in _PROVIDER_DEFINITIONS:
            row = by_provider.get(provider)
            public = row.public_config if row and isinstance(row.public_config, dict) else {}
            state = "coming_soon"
            if available:
                state = "connected" if row and row.status == "active" else "not_configured"
                if row and row.last_error_code:
                    state = "error"
            items.append(
                AnalyticsConnectionItem(
                    provider=provider,
                    label=label,
                    description=description,
                    state=state,
                    available=available,
                    credentials_configured=bool(row and row.encrypted_credentials),
                    counter_id=str(public.get("counter_id") or "") or None,
                    counter_name=str(public.get("counter_name") or "") or None,
                    site=str(public.get("site") or "") or None,
                    last_verified_at=row.last_verified_at if row else None,
                    last_error_code=row.last_error_code if row else None,
                )
            )
        return items

    async def upsert_yandex_metrika(
        self,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        counter_id: str,
        oauth_token: str | None,
        actor_staff_user_id: int | None,
        actor_username: str,
    ) -> AnalyticsConnectionItem:
        existing = await self._get_connection(
            session,
            tenant_scope=tenant_scope,
            provider=YANDEX_METRIKA,
            for_update=True,
        )
        token = (oauth_token or "").strip()
        if token and (len(token) < 16 or len(token) > 4096):
            raise AnalyticsConnectionError(
                "invalid_oauth_token_format",
                "OAuth-токен имеет некорректную длину",
            )
        if not token and existing:
            token = AnalyticsCredentialCipher.decrypt(existing.encrypted_credentials).get(
                "oauth_token", ""
            )
        if not token:
            raise AnalyticsConnectionError(
                "oauth_token_required",
                "Укажите OAuth-токен Яндекс Метрики",
            )

        counter = await self._verify_yandex_metrika(
            counter_id=counter_id,
            oauth_token=token,
        )
        now = datetime.now(timezone.utc)
        connection = existing or AnalyticsConnection(
            tenant_id=tenant_scope.tenant_id,
            storefront_id=tenant_scope.storefront_id,
            provider=YANDEX_METRIKA,
            encrypted_credentials="",
            credentials_fingerprint="",
        )
        before_counter = (
            str(connection.public_config.get("counter_id") or "")
            if isinstance(connection.public_config, dict)
            else ""
        )
        credential_replaced = not existing or bool(oauth_token)
        connection.status = "active"
        connection.public_config = {
            "counter_id": counter_id,
            "counter_name": str(counter.get("name") or ""),
            "site": str(counter.get("site") or ""),
        }
        connection.encrypted_credentials = AnalyticsCredentialCipher.encrypt(
            {"oauth_token": token}
        )
        connection.credentials_fingerprint = AnalyticsCredentialCipher.fingerprint(token)
        connection.last_verified_at = now
        connection.last_error_code = None
        connection.updated_at = now
        session.add(connection)
        await session.flush()
        session.add(
            TenantAuditEvent(
                tenant_id=tenant_scope.tenant_id,
                storefront_id=tenant_scope.storefront_id,
                actor_staff_user_id=actor_staff_user_id,
                actor_username=actor_username,
                action="analytics_connection.updated" if existing else "analytics_connection.created",
                entity_type="analytics_connection",
                entity_id=int(connection.id or 0),
                request_id=current_request_id(),
                change_set={
                    "provider": YANDEX_METRIKA,
                    "counter_id": {"before": before_counter or None, "after": counter_id},
                    "credential_replaced": credential_replaced,
                    "verified": True,
                },
            )
        )
        await session.commit()
        await session.refresh(connection)
        return (await self.list_connections(session, tenant_scope=tenant_scope))[0]

    async def _verify_yandex_metrika(
        self,
        *,
        counter_id: str,
        oauth_token: str,
    ) -> dict[str, Any]:
        try:
            async with self._client_factory() as client:
                response = await client.get(
                    self.METRIKA_COUNTER_URL.format(counter_id=counter_id),
                    headers={"Authorization": f"OAuth {oauth_token}"},
                )
        except httpx.HTTPError as exc:
            raise AnalyticsConnectionError(
                "provider_unavailable",
                "Яндекс Метрика временно недоступна. Попробуйте ещё раз.",
                status_code=502,
            ) from exc
        if response.status_code == 401:
            raise AnalyticsConnectionError(
                "invalid_oauth_token",
                "OAuth-токен недействителен или отозван",
            )
        if response.status_code in {403, 404}:
            raise AnalyticsConnectionError(
                "counter_access_denied",
                "У этого аккаунта нет доступа к указанному счётчику",
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise AnalyticsConnectionError(
                "provider_error",
                "Яндекс Метрика не подтвердила подключение",
                status_code=502,
            ) from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise AnalyticsConnectionError(
                "provider_response_invalid",
                "Яндекс Метрика вернула некорректный ответ",
                status_code=502,
            ) from exc
        counter = payload.get("counter") if isinstance(payload, dict) else None
        if not isinstance(counter, dict):
            raise AnalyticsConnectionError(
                "provider_response_invalid",
                "Яндекс Метрика вернула некорректный ответ",
                status_code=502,
            )
        return counter

    @classmethod
    async def get_metrika_runtime_credentials(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> AnalyticsRuntimeCredentials | None:
        connection = await cls._get_connection(
            session,
            tenant_scope=tenant_scope,
            provider=YANDEX_METRIKA,
        )
        if connection is None or connection.status != "active":
            return None
        public = connection.public_config if isinstance(connection.public_config, dict) else {}
        counter_id = str(public.get("counter_id") or "").strip()
        credentials = AnalyticsCredentialCipher.decrypt(connection.encrypted_credentials)
        oauth_token = credentials.get("oauth_token", "").strip()
        if not counter_id.isdigit() or not oauth_token:
            return None
        return AnalyticsRuntimeCredentials(
            counter_id=counter_id,
            oauth_token=oauth_token,
            fingerprint=connection.credentials_fingerprint,
        )
