from types import SimpleNamespace

import pytest

from services.importer_service import ImporterService


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self, existing_product):
        self._existing_product = existing_product

    async def execute(self, stmt):  # noqa: ARG002
        return _FakeScalarResult(self._existing_product)

    async def refresh(self, obj, attribute_names=None):  # noqa: ARG002
        return None


class _FakeSessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_import_product_existing_collects_related_when_requested(monkeypatch):
    existing = SimpleNamespace(
        id=123,
        tags=[SimpleNamespace(slug="cat-household")],
    )
    fake_session = _FakeSession(existing)

    parser_calls = {"count": 0}

    class _FakeParser:
        async def parse(self, url):  # noqa: ARG002
            parser_calls["count"] += 1
            return {"related_urls": ["https://lg24.by/product/sibling/"]}

    monkeypatch.setattr(
        "services.importer_service.async_session_maker",
        lambda: _FakeSessionContext(fake_session),
    )

    service = ImporterService()
    service.get_parser = lambda url: _FakeParser()  # noqa: ARG005

    result = await service.import_product(
        "https://lg24.by/product/current/",
        update_existing=False,
        collect_related=True,
    )

    assert result["product"] is existing
    assert result["related_urls"] == ["https://lg24.by/product/sibling/"]
    assert parser_calls["count"] == 1

