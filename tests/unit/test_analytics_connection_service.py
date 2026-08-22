from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import AnalyticsConnection, Tenant, TenantAuditEvent
from models.tenancy import Storefront, TenantScope
from services.analytics_connection_service import (
    AnalyticsConnectionError,
    AnalyticsConnectionService,
    AnalyticsCredentialCipher,
)


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
        session.add_all([tenant, *storefronts])
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
    assert AnalyticsCredentialCipher.decrypt(stored.encrypted_credentials) == {
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
