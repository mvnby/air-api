from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import AnalyticsConnection, Tenant, TenantAuditEvent
from models.tenancy import Storefront, StorefrontDomain, TenantScope
from services.analytics_connection_service import (
    AnalyticsConnectionError,
    AnalyticsConnectionService,
    AnalyticsCredentialCipher,
)
from services.integration_credential_health import integration_credential_health


@pytest.fixture
async def analytics_session(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'analytics-connections.db'}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)

    factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        tenant = Tenant(id=21, slug="vitebsk", display_name="Витебск")
        storefronts = [
            Storefront(
                id=71,
                tenant_id=21,
                slug="vitebsk",
                display_name="Витебск",
                status="active",
                is_default=True,
            ),
            Storefront(
                id=72,
                tenant_id=21,
                slug="polotsk",
                display_name="Полоцк",
                status="active",
            ),
        ]
        session.add_all([
            tenant,
            *storefronts,
            StorefrontDomain(
                id=171,
                storefront_id=71,
                hostname="mvn.by",
                status="active",
                is_primary=True,
            ),
        ])
        await session.commit()
        yield session

    await engine.dispose()


def _service(handler):
    return AnalyticsConnectionService(
        client_factory=lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        )
    )


@pytest.mark.asyncio
async def test_metrika_connection_is_encrypted_and_exactly_storefront_scoped(
    analytics_session,
):
    token = "test-oauth-token-that-must-never-be-stored-in-plaintext"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"OAuth {token}"
        assert request.url.path.endswith("/counter/123456")
        return httpx.Response(
            200,
            json={
                "counter": {
                    "id": 123456,
                    "name": "Мастер Воздуха Витебск",
                    "site": "mvn.by",
                }
            },
        )

    scope = TenantScope(tenant_id=21, storefront_id=71)
    connected = await _service(handler).upsert_yandex_metrika(
        analytics_session,
        tenant_scope=scope,
        counter_id="123456",
        oauth_token=token,
        actor_staff_user_id=5,
        actor_username="owner",
    )

    assert connected.state == "connected"
    assert connected.counter_name == "Мастер Воздуха Витебск"
    stored = (
        await analytics_session.execute(select(AnalyticsConnection))
    ).scalar_one()
    assert token not in stored.encrypted_credentials
    assert AnalyticsCredentialCipher.decrypt(stored.encrypted_credentials, tenant_id=stored.tenant_id, storefront_id=stored.storefront_id, provider=stored.provider) == {
        "oauth_token": token
    }

    runtime = await AnalyticsConnectionService.get_metrika_runtime_credentials(
        analytics_session,
        tenant_scope=scope,
    )
    assert runtime is not None
    assert runtime.counter_id == "123456"
    assert runtime.oauth_token == token
    assert await AnalyticsConnectionService.get_metrika_runtime_credentials(
        analytics_session,
        tenant_scope=TenantScope(tenant_id=21, storefront_id=72),
    ) is None

    audit = (
        await analytics_session.execute(select(TenantAuditEvent))
    ).scalar_one()
    assert token not in str(audit.change_set)
    assert audit.change_set["counter_id"]["after"] == "123456"
    assert await integration_credential_health(analytics_session) == {
        "status": "passed", "checked": 1, "unreadable": 0,
    }


@pytest.mark.asyncio
async def test_invalid_metrika_token_is_not_persisted(analytics_session):
    service = _service(lambda _request: httpx.Response(401, json={"error": "unauthorized"}))

    with pytest.raises(AnalyticsConnectionError) as exc_info:
        await service.upsert_yandex_metrika(
            analytics_session,
            tenant_scope=TenantScope(tenant_id=21, storefront_id=71),
            counter_id="123456",
            oauth_token="invalid-oauth-token-value",
            actor_staff_user_id=5,
            actor_username="owner",
        )

    assert exc_info.value.code == "invalid_oauth_token"
    assert (
        await analytics_session.execute(select(AnalyticsConnection))
    ).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_invalid_token_length_is_rejected_before_provider_call(analytics_session):
    def unexpected_handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("invalid secret must not be sent to the provider")

    with pytest.raises(AnalyticsConnectionError) as exc_info:
        await _service(unexpected_handler).upsert_yandex_metrika(
            analytics_session,
            tenant_scope=TenantScope(tenant_id=21, storefront_id=71),
            counter_id="123456",
            oauth_token="short",
            actor_staff_user_id=5,
            actor_username="owner",
        )

    assert exc_info.value.code == "invalid_oauth_token_format"


@pytest.mark.asyncio
async def test_yandex_direct_connection_is_verified_encrypted_and_scoped(analytics_session):
    token = "direct-oauth-token-that-must-stay-encrypted"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/campaigns")
        assert request.headers["authorization"] == f"Bearer {token}"
        assert request.headers["client-login"] == "vitebsk-client"
        return httpx.Response(200, json={"result": {"Campaigns": [{"Id": 17}]}})

    scope = TenantScope(tenant_id=21, storefront_id=71)
    item = await _service(handler).upsert_yandex_direct(
        analytics_session,
        tenant_scope=scope,
        client_login="vitebsk-client",
        oauth_token=token,
        actor_staff_user_id=5,
        actor_username="owner",
    )

    assert item.state == "connected"
    assert item.configuration["client_login"] == "vitebsk-client"
    row = (
        await analytics_session.execute(
            select(AnalyticsConnection).where(
                AnalyticsConnection.provider == "yandex_direct"
            )
        )
    ).scalar_one()
    assert token not in row.encrypted_credentials
    assert AnalyticsCredentialCipher.decrypt(row.encrypted_credentials, tenant_id=row.tenant_id, storefront_id=row.storefront_id, provider=row.provider)["oauth_token"] == token


@pytest.mark.asyncio
async def test_yandex_webmaster_uses_exact_active_primary_domain(analytics_session):
    token = "webmaster-oauth-token-that-must-stay-encrypted"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"OAuth {token}"
        if request.url.path.endswith("/v4/user"):
            return httpx.Response(200, json={"user_id": 42})
        return httpx.Response(
            200,
            json={
                "hosts": [
                    {
                        "host_id": "https:mvn.by:443",
                        "ascii_host_url": "https://mvn.by/",
                        "verified": True,
                    },
                    {
                        "host_id": "https:polotsk.example:443",
                        "ascii_host_url": "https://polotsk.example/",
                        "verified": True,
                    },
                ]
            },
        )

    item = await _service(handler).upsert_yandex_webmaster(
        analytics_session,
        tenant_scope=TenantScope(tenant_id=21, storefront_id=71),
        oauth_token=token,
        actor_staff_user_id=5,
        actor_username="owner",
    )

    assert item.state == "connected"
    assert item.configuration["host_id"] == "https:mvn.by:443"
    assert item.configuration["primary_hostname"] == "mvn.by"


@pytest.mark.asyncio
async def test_google_oauth_payload_is_encrypted_without_secret_audit(analytics_session):
    credentials = {
        "kind": "google_oauth_v1",
        "access_token": "google-access-secret",
        "refresh_token": "google-refresh-secret",
        "client_id": "client-id",
        "client_secret": "google-client-secret",
        "token_uri": "https://oauth2.googleapis.com/token",
        "expiry": None,
        "scopes": ["https://www.googleapis.com/auth/analytics.readonly"],
    }
    item = await AnalyticsConnectionService.persist_google_connection(
        analytics_session,
        tenant_scope=TenantScope(tenant_id=21, storefront_id=71),
        provider="google_analytics",
        public_config={"property_id": "123456789"},
        credentials=credentials,
        actor_staff_user_id=5,
        actor_username="owner",
    )

    assert item.state == "connected"
    row = (
        await analytics_session.execute(
            select(AnalyticsConnection).where(
                AnalyticsConnection.provider == "google_analytics"
            )
        )
    ).scalar_one()
    assert "google-refresh-secret" not in row.encrypted_credentials
    assert AnalyticsCredentialCipher.decrypt(row.encrypted_credentials, tenant_id=row.tenant_id, storefront_id=row.storefront_id, provider=row.provider) == credentials
    audits = (
        await analytics_session.execute(
            select(TenantAuditEvent).where(
                TenantAuditEvent.entity_id == row.id,
                TenantAuditEvent.action == "analytics_connection.created",
            )
        )
    ).scalars().all()
    assert audits
    assert "google-refresh-secret" not in str(audits[-1].change_set)


@pytest.mark.asyncio
async def test_unreadable_connection_remains_configured_with_error(analytics_session, caplog):
    row = AnalyticsConnection(
        tenant_id=21, storefront_id=71, provider="yandex_metrika",
        public_config={"counter_id": "123456"},
        encrypted_credentials="unreadable-sensitive-ciphertext",
        credentials_fingerprint="original-fingerprint",
    )
    analytics_session.add(row)
    await analytics_session.commit()
    scope = TenantScope(tenant_id=21, storefront_id=71)

    items = await AnalyticsConnectionService.list_connections(analytics_session, tenant_scope=scope)
    item = next(item for item in items if item.provider == "yandex_metrika")
    assert item.state == "error"
    assert item.credentials_configured is True
    assert item.last_error_code == "credentials_unreadable"

    connections = await AnalyticsConnectionService.get_runtime_connections(analytics_session, tenant_scope=scope)
    assert connections["yandex_metrika"].error_code == "credentials_unreadable"
    assert connections["yandex_metrika"].credentials == {}
    assert "ANALYTICS_CREDENTIALS_UNAVAILABLE" in caplog.text
    assert "unreadable-sensitive-ciphertext" not in caplog.text
    assert await AnalyticsConnectionService.get_runtime_connections(
        analytics_session, tenant_scope=TenantScope(tenant_id=21, storefront_id=72)
    ) == {}
    with pytest.raises(AnalyticsConnectionError) as error:
        await AnalyticsConnectionService.get_metrika_runtime_credentials(analytics_session, tenant_scope=scope)
    assert error.value.code == "credentials_unreadable"
    # Reading health does not rewrite the saved connection or discard credentials.
    await analytics_session.refresh(row)
    assert row.status == "active"
    assert row.last_error_code is None
    assert row.encrypted_credentials == "unreadable-sensitive-ciphertext"
    assert await integration_credential_health(analytics_session) == {
        "status": "failed", "checked": 1, "unreadable": 1,
    }
