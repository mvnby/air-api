from dataclasses import replace
from datetime import date

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func
from sqlmodel import select

from core.config import settings
from core.database import get_session
from core.security import AuthenticatedUser, require_manager_access
from models import IntegrationOutboxEvent
from models.call_recording import CallDriveConnection, CallRecording
from routers.manager_call_recordings import router
from services import call_drive_connection_service
from services.call_recording_picker import CallRecordingPicker
from tests.integration.test_call_recording_pipeline import context, FILE_ID, FOLDER_ID


def client_app(factory, actor, auth_box):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_manager_access] = lambda: auth_box[0]
    async def sessions():
        async with factory() as session:
            yield session
    app.dependency_overrides[get_session] = sessions
    return app


@pytest.mark.asyncio
async def test_picker_api_filters_original_days_phone_and_never_queues(context, monkeypatch):
    factory, actor, provider = context
    monkeypatch.setattr(call_drive_connection_service, "get_call_drive_provider", lambda: provider)
    monkeypatch.setattr(settings, "CALL_RECORDINGS_ENABLED", False)
    seen = []
    async def listing(folder, **kwargs):
        seen.append((folder, kwargs))
        base = await provider.metadata(FILE_ID)
        return [
            {**base, "id": "contact-file-00000001", "name": "Вызов Дима Кондиционерщик_261008_170514.m4a"},
            {**base, "id": "phone-file-000000001", "name": "Вызов +375291234567_261008_000014.m4a"},
            {**base, "id": "old-file-0000000001", "name": "Вызов Дима_261007_170514.m4a"},
            {**base, "id": "unknown-file-000001", "name": "Вызов Дима.m4a"},
        ], None
    monkeypatch.setattr(provider, "list_recordings", listing)
    auth = [AuthenticatedUser(username=actor.username, auth_source="staff", staff_user_id=actor.staff_user_id, role="manager", tenant_id=1, storefront_id=1)]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(client_app(factory, actor, auth)), base_url="http://test") as client:
        path = "/api/manager/call-recordings/drive/files"
        response = await client.get(path, params={"date_from": "2026-10-08", "date_to": "2026-10-08"})
        assert response.status_code == 200
        result = response.json()
        assert [item["file_id"] for item in result["items"]] == ["contact-file-00000001", "phone-file-000000001"]
        assert result["items"][0]["contact"] == "Дима Кондиционерщик" and result["items"][1]["phone"] == "+375291234567"
        assert "secret-test-token" not in response.text
        response = await client.get(path, params={"query": "+375 (29) 123-45"})
        assert len(response.json()["items"]) == 1
        assert (await client.get(path, params={"date_from": "2026-10-09", "date_to": "2026-10-08"})).status_code == 422
        assert (await client.get(path, params={"query": "x" * 101})).status_code == 422
        assert (await client.get(path, params={"page_token": "x" * 2049})).status_code == 422
        before = len(seen)
        auth[0] = replace(auth[0], staff_user_id=actor.staff_user_id + 1000, role="owner")
        assert (await client.get(path)).status_code == 403
        assert len(seen) == before
    assert provider.downloads == 0
    assert all(folder == FOLDER_ID and kw["page_size"] == 100 for folder, kw in seen)
    async with factory() as session:
        connection = await session.scalar(select(CallDriveConnection))
        assert connection.page_token is None and not connection.auto_poll_enabled
        assert await session.scalar(select(func.count()).select_from(CallRecording)) == 0
        assert await session.scalar(select(func.count()).select_from(IntegrationOutboxEvent)) == 0


@pytest.mark.asyncio
async def test_picker_bounded_empty_search_can_continue_beyond_first_pages(context, monkeypatch):
    factory, actor, provider = context
    seen = []
    async def listing(folder, *, page_token=None, page_size=100):
        page = int(page_token or "0")
        seen.append(page)
        base = await provider.metadata(FILE_ID)
        name = "Вызов Искомый_260930_230014.m4a" if page == 5 else "Вызов Другой_261008_170514.m4a"
        return [{**base, "name": name}], str(page + 1) if page < 5 else None
    monkeypatch.setattr(provider, "list_recordings", listing)
    async with factory() as session:
        first = await CallRecordingPicker.list_files(session, actor, date_from=date(2026, 9, 30), date_to=date(2026, 9, 30), query="искомый", provider=provider)
        assert not first.items and first.next_page_token == "5" and seen == [0, 1, 2, 3, 4]
        last = await CallRecordingPicker.list_files(session, actor, date_from=date(2026, 9, 30), date_to=date(2026, 9, 30), query="искомый", page_token=first.next_page_token, provider=provider)
        assert len(last.items) == 1 and last.next_page_token is None and seen[-1] == 5


@pytest.mark.asyncio
async def test_picker_rechecks_private_access_after_drive_io(context, monkeypatch):
    factory, actor, provider = context
    async def listing(*args, **kwargs):
        monkeypatch.setattr(settings, "CALL_RECORDINGS_PILOT_STAFF_IDS", [])
        return [await provider.metadata(FILE_ID)], None
    monkeypatch.setattr(provider, "list_recordings", listing)
    async with factory() as session:
        with pytest.raises(PermissionError):
            await CallRecordingPicker.list_files(session, actor, provider=provider)
