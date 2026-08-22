from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from core.request_context import current_request_id
from models import AnalyticsConnection, StorefrontDomain, TenantAuditEvent
from models.tenancy import TenantScope
from schemas_analytics import AnalyticsConnectionItem
from services.analytics_connection_contracts import (
    GOOGLE_ADS,
    GOOGLE_ANALYTICS,
    GOOGLE_SEARCH_CONSOLE,
    PROVIDER_DEFINITIONS,
    YANDEX_DIRECT,
    YANDEX_METRIKA,
    YANDEX_WEBMASTER,
    AnalyticsConnectionError,
    AnalyticsCredentialCipher,
    AnalyticsRuntimeConnection,
    AnalyticsRuntimeCredentials,
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
        for provider, label, description, available in PROVIDER_DEFINITIONS:
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
                    configuration={
                        str(key): str(value)
                        for key, value in public.items()
                        if value is not None and str(value).strip()
                    },
                )
            )
        return items

    @classmethod
    async def _item_for_provider(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        provider: str,
    ) -> AnalyticsConnectionItem:
        items = await cls.list_connections(session, tenant_scope=tenant_scope)
        return next(item for item in items if item.provider == provider)

    @classmethod
    async def _persist_connection(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        provider: str,
        public_config: dict[str, str],
        credentials: dict[str, Any],
        actor_staff_user_id: int | None,
        actor_username: str,
        credential_replaced: bool,
    ) -> AnalyticsConnectionItem:
        existing = await cls._get_connection(
            session,
            tenant_scope=tenant_scope,
            provider=provider,
            for_update=True,
        )
        now = datetime.now(timezone.utc)
        connection = existing or AnalyticsConnection(
            tenant_id=tenant_scope.tenant_id,
            storefront_id=tenant_scope.storefront_id,
            provider=provider,
            encrypted_credentials="",
            credentials_fingerprint="",
        )
        before_config = (
            dict(connection.public_config)
            if isinstance(connection.public_config, dict)
            else {}
        )
        fingerprint_source = json.dumps(
            credentials,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        connection.status = "active"
        connection.public_config = dict(public_config)
        connection.encrypted_credentials = AnalyticsCredentialCipher.encrypt(credentials)
        connection.credentials_fingerprint = AnalyticsCredentialCipher.fingerprint(
            fingerprint_source
        )
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
                    "provider": provider,
                    "public_config": {"before": before_config, "after": public_config},
                    "credential_replaced": credential_replaced,
                    "verified": True,
                },
            )
        )
        await session.commit()
        return await cls._item_for_provider(
            session,
            tenant_scope=tenant_scope,
            provider=provider,
        )

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
            token = str(
                AnalyticsCredentialCipher.decrypt(existing.encrypted_credentials).get(
                    "oauth_token", ""
                )
            ).strip()
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

    async def upsert_yandex_direct(
        self,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        client_login: str | None,
        oauth_token: str | None,
        actor_staff_user_id: int | None,
        actor_username: str,
    ) -> AnalyticsConnectionItem:
        from services.analytics_yandex_providers import YandexDirectProvider

        existing = await self._get_connection(
            session,
            tenant_scope=tenant_scope,
            provider=YANDEX_DIRECT,
        )
        token = self._resolve_secret(existing, oauth_token, "oauth_token")
        normalized_login = str(client_login or "").strip()
        try:
            verified = await YandexDirectProvider(client_factory=self._client_factory).verify(
                oauth_token=token,
                client_login=normalized_login or None,
            )
        except Exception as exc:
            raise self._provider_error(exc, provider_label="Яндекс Директ") from exc
        public_config = {
            "client_login": normalized_login,
            **{str(key): str(value) for key, value in verified.items() if value is not None},
        }
        return await self._persist_connection(
            session,
            tenant_scope=tenant_scope,
            provider=YANDEX_DIRECT,
            public_config=public_config,
            credentials={"oauth_token": token},
            actor_staff_user_id=actor_staff_user_id,
            actor_username=actor_username,
            credential_replaced=not existing or bool(oauth_token),
        )

    async def upsert_yandex_webmaster(
        self,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        oauth_token: str | None,
        actor_staff_user_id: int | None,
        actor_username: str,
    ) -> AnalyticsConnectionItem:
        from services.analytics_yandex_providers import YandexWebmasterProvider

        existing = await self._get_connection(
            session,
            tenant_scope=tenant_scope,
            provider=YANDEX_WEBMASTER,
        )
        token = self._resolve_secret(existing, oauth_token, "oauth_token")
        domain = (
            await session.execute(
                select(StorefrontDomain).where(
                    StorefrontDomain.storefront_id == tenant_scope.storefront_id,
                    StorefrontDomain.is_primary.is_(True),
                    StorefrontDomain.status == "active",
                )
            )
        ).scalar_one_or_none()
        if domain is None:
            raise AnalyticsConnectionError(
                "storefront_domain_unavailable",
                "У филиала не настроен активный основной домен",
            )
        try:
            verified = await YandexWebmasterProvider(client_factory=self._client_factory).verify(
                oauth_token=token,
                primary_hostname=domain.hostname,
            )
        except Exception as exc:
            raise self._provider_error(exc, provider_label="Яндекс Вебмастер") from exc
        return await self._persist_connection(
            session,
            tenant_scope=tenant_scope,
            provider=YANDEX_WEBMASTER,
            public_config={
                "primary_hostname": domain.hostname,
                **{str(key): str(value) for key, value in verified.items() if value is not None},
            },
            credentials={"oauth_token": token},
            actor_staff_user_id=actor_staff_user_id,
            actor_username=actor_username,
            credential_replaced=not existing or bool(oauth_token),
        )

    @staticmethod
    def _resolve_secret(
        existing: AnalyticsConnection | None,
        supplied: str | None,
        key: str,
    ) -> str:
        secret = str(supplied or "").strip()
        if secret and not 16 <= len(secret) <= 8192:
            raise AnalyticsConnectionError(
                "invalid_oauth_token_format",
                "OAuth-токен имеет некорректную длину",
            )
        if not secret and existing is not None:
            secret = str(
                AnalyticsCredentialCipher.decrypt(existing.encrypted_credentials).get(
                    key, ""
                )
            ).strip()
        if not secret:
            raise AnalyticsConnectionError(
                "oauth_token_required",
                "Укажите OAuth-токен",
            )
        return secret

    @staticmethod
    def _provider_error(exc: Exception, *, provider_label: str) -> AnalyticsConnectionError:
        from services.analytics_provider_types import AnalyticsProviderError

        if not isinstance(exc, AnalyticsProviderError):
            return AnalyticsConnectionError(
                "provider_unavailable",
                f"{provider_label} временно недоступен. Попробуйте ещё раз.",
                status_code=502,
            )
        if exc.code.endswith("host_not_verified"):
            message = "Основной домен филиала не подтверждён в Яндекс Вебмастере"
        elif exc.code.endswith("access_denied"):
            message = f"{provider_label} отклонил токен или у аккаунта нет доступа"
        elif exc.code.endswith("config_invalid"):
            message = f"Параметры подключения {provider_label} некорректны"
        else:
            message = (
                f"{provider_label} временно недоступен. Попробуйте ещё раз."
                if exc.retryable
                else f"{provider_label} не подтвердил подключение"
            )
        return AnalyticsConnectionError(
            exc.code,
            message,
            status_code=502 if exc.retryable else 422,
        )

    @classmethod
    async def persist_google_connection(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        provider: str,
        public_config: dict[str, str],
        credentials: dict[str, Any],
        actor_staff_user_id: int | None,
        actor_username: str,
    ) -> AnalyticsConnectionItem:
        if provider not in {GOOGLE_ANALYTICS, GOOGLE_ADS, GOOGLE_SEARCH_CONSOLE}:
            raise AnalyticsConnectionError("unsupported_provider", "Провайдер не поддерживается")
        return await cls._persist_connection(
            session,
            tenant_scope=tenant_scope,
            provider=provider,
            public_config=public_config,
            credentials=credentials,
            actor_staff_user_id=actor_staff_user_id,
            actor_username=actor_username,
            credential_replaced=True,
        )

    @classmethod
    async def get_runtime_connections(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> dict[str, AnalyticsRuntimeConnection]:
        rows = (
            await session.execute(
                select(AnalyticsConnection).where(
                    AnalyticsConnection.tenant_id == tenant_scope.tenant_id,
                    AnalyticsConnection.storefront_id == tenant_scope.storefront_id,
                    AnalyticsConnection.status == "active",
                )
            )
        ).scalars().all()
        connections: dict[str, AnalyticsRuntimeConnection] = {}
        for row in rows:
            public = row.public_config if isinstance(row.public_config, dict) else {}
            try:
                credentials = AnalyticsCredentialCipher.decrypt(row.encrypted_credentials)
            except AnalyticsConnectionError:
                continue
            connections[row.provider] = AnalyticsRuntimeConnection(
                provider=row.provider,
                public_config={str(key): str(value) for key, value in public.items()},
                credentials=credentials,
                fingerprint=row.credentials_fingerprint,
            )
        return connections

    @classmethod
    async def persist_refreshed_credentials(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        provider: str,
        credentials: dict[str, Any],
    ) -> None:
        connection = await cls._get_connection(
            session,
            tenant_scope=tenant_scope,
            provider=provider,
            for_update=True,
        )
        if connection is None or connection.status != "active":
            return
        serialized = json.dumps(
            credentials,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        connection.encrypted_credentials = AnalyticsCredentialCipher.encrypt(credentials)
        connection.credentials_fingerprint = AnalyticsCredentialCipher.fingerprint(serialized)
        connection.updated_at = datetime.now(timezone.utc)
        session.add(connection)
        await session.commit()

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
        try:
            credentials = AnalyticsCredentialCipher.decrypt(connection.encrypted_credentials)
        except AnalyticsConnectionError:
            return None
        oauth_token = str(credentials.get("oauth_token", "")).strip()
        if not counter_id.isdigit() or not oauth_token:
            return None
        return AnalyticsRuntimeCredentials(
            counter_id=counter_id,
            oauth_token=oauth_token,
            fingerprint=connection.credentials_fingerprint,
        )
