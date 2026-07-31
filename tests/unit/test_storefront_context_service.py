from unittest.mock import AsyncMock

import pytest

from crud.tenancy import StorefrontContextRow
from services.storefront_context_service import (
    InvalidStorefrontHostError,
    StorefrontContextService,
)


@pytest.mark.parametrize(
    ("raw_host", "expected"),
    [
        ("mvn.by", "mvn.by"),
        ("MVN.BY:443", "mvn.by"),
        ("www.mvn.by.", "www.mvn.by"),
        ("пример.бел", "xn--e1afmkfd.xn--90ais"),
        ("localhost:8000", "localhost"),
    ],
)
def test_normalize_hostname_accepts_domain_and_optional_port(raw_host, expected):
    assert StorefrontContextService.normalize_hostname(raw_host) == expected


@pytest.mark.parametrize(
    "raw_host",
    [
        "",
        "https://mvn.by",
        "mvn.by/path",
        "user@mvn.by",
        "mvn.by,evil.example",
        "bad_label.mvn.by",
        "-bad.mvn.by",
        "mvn.by:",
        "mvn.by:99999",
    ],
)
def test_normalize_hostname_rejects_untrusted_host_syntax(raw_host):
    with pytest.raises(InvalidStorefrontHostError):
        StorefrontContextService.normalize_hostname(raw_host)


@pytest.mark.asyncio
async def test_resolve_by_host_returns_typed_context(monkeypatch):
    session = object()
    dao = AsyncMock(
        return_value=StorefrontContextRow(
            tenant_id=1,
            tenant_slug="mvn",
            tenant_kind="operator",
            storefront_id=2,
            storefront_slug="main",
            storefront_name="MVN",
            hostname="mvn.by",
            city="Витебск",
            default_locale="ru-BY",
            currency="BYN",
        )
    )
    monkeypatch.setattr(
        "services.storefront_context_service.TenancyDAO.get_active_storefront_by_hostname",
        dao,
    )

    context = await StorefrontContextService.resolve_by_host(session, "MVN.BY:443")

    assert context is not None
    assert context.tenant_slug == "mvn"
    assert context.storefront_slug == "main"
    assert context.hostname == "mvn.by"
    dao.assert_awaited_once_with(session, "mvn.by")


@pytest.mark.asyncio
async def test_resolve_by_host_returns_none_for_unknown_domain(monkeypatch):
    dao = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "services.storefront_context_service.TenancyDAO.get_active_storefront_by_hostname",
        dao,
    )

    assert await StorefrontContextService.resolve_by_host(object(), "unknown.example") is None


@pytest.mark.asyncio
async def test_resolve_by_scope_returns_public_context(monkeypatch):
    session = object()
    row = StorefrontContextRow(
        tenant_id=1,
        tenant_slug="mvn",
        tenant_kind="operator",
        storefront_id=2,
        storefront_slug="orsha",
        storefront_name="MVN Орша",
        hostname="orsha.mvn.by",
        city="Орша",
        default_locale="ru-BY",
        currency="BYN",
        tenant_is_system=True,
    )
    resolver = AsyncMock(return_value=row)
    monkeypatch.setattr(
        "services.storefront_context_service.TenancyDAO.get_active_storefront_by_scope",
        resolver,
    )

    context = await StorefrontContextService.resolve_by_scope(
        session,
        tenant_id=1,
        storefront_id=2,
    )

    assert context is not None
    assert context.storefront_name == "MVN Орша"
    assert context.tenant_is_system is True
    resolver.assert_awaited_once_with(
        session,
        tenant_id=1,
        storefront_id=2,
    )
