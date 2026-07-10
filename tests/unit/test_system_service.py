import pytest

from services import system_service as system_service_module
from services.system_service import SystemService


@pytest.mark.asyncio
async def test_trigger_web_rebuild_sends_catalog_revision_input(monkeypatch):
    captured: dict[str, object] = {}

    class DummyResponse:
        status_code = 204
        content = b""

    class DummyAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, headers, json, timeout):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            captured["timeout"] = timeout
            return DummyResponse()

    monkeypatch.setattr(system_service_module.settings, "GITHUB_TOKEN", "token")
    monkeypatch.setattr(system_service_module.settings, "GITHUB_OWNER", "owner")
    monkeypatch.setattr(system_service_module.settings, "GITHUB_REPO", "repo")
    monkeypatch.setattr(system_service_module.httpx, "AsyncClient", lambda: DummyAsyncClient())

    result = await SystemService.trigger_web_rebuild(catalog_revision=17)

    assert result == {"success": True}
    assert captured["url"] == (
        "https://api.github.com/repos/owner/repo/actions/workflows/rebuild-web.yml/dispatches"
    )
    assert captured["json"] == {
        "ref": "main",
        "inputs": {"catalog_revision": "17"},
    }
    assert captured["timeout"] == 10.0


@pytest.mark.asyncio
async def test_trigger_web_rebuild_reports_missing_token(monkeypatch):
    monkeypatch.setattr(system_service_module.settings, "GITHUB_TOKEN", "")

    result = await SystemService.trigger_web_rebuild(catalog_revision=17)

    assert result == {"success": False, "error": "GITHUB_TOKEN_MISSING"}
