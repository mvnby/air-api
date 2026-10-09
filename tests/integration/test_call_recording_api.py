from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from core.database import get_session
from core.config import settings
from core.security import AuthenticatedUser, require_manager_access
from models import StaffUser, Tenant, TenantMembership
from routers.manager_call_recordings import router
from services import call_drive_oauth
from services.call_recording_service import CallRecordingService
from services.call_recording_job_service import CallRecordingJobService
from tests.integration.test_call_recording_pipeline import context, queue, runner


@pytest.mark.asyncio
async def test_api_personal_scope_and_selected_proposal_adoption(context, monkeypatch):
    factory, actor, provider = context
    recording_id = await queue(context)
    run, calls = runner(context)
    await CallRecordingJobService.process_batch(worker_id="http-fixture", session_factory=factory, runner=run)
    auth = AuthenticatedUser(username=actor.username, auth_source="staff", staff_user_id=actor.staff_user_id, role="manager", tenant_id=1, storefront_id=1, auth_version=1)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_manager_access] = lambda: auth
    async def sessions():
        async with factory() as session:
            yield session
    app.dependency_overrides[get_session] = sessions
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        status = await client.get("/api/manager/call-recordings/connection")
        assert status.status_code == 200 and "secret-test-token" not in status.text
        assert "encrypted_credentials" not in status.text
        assert (await client.get("/api/manager/call-recordings?limit=101")).status_code == 422
        read = await client.get(f"/api/manager/call-recordings/{recording_id}")
        assert read.status_code == 200
        material = read.json()
        proposal = material["proposals"][1]
        url = f"/api/manager/call-recordings/{recording_id}/proposals/{proposal['id']}/adopt"
        payload = {"expected_version": material["version"], "task": proposal["payload"]}
        assert (await client.post(url, json=payload)).status_code == 200
        assert (await client.post(url, json=payload)).json()["replayed"] is True
        auth = replace(auth, demo_read_only=True)
        assert (await client.post(url, json=payload)).status_code == 403
        auth = replace(auth, demo_read_only=False)
        async with factory() as session:
            other = StaffUser(username="http-other", display_name="Другой менеджер", roles=["manager"], primary_role="manager")
            session.add(other)
            await session.flush()
            session.add(TenantMembership(staff_user_id=other.id, tenant_id=1, role="owner", status="active"))
            await session.commit()
            auth = replace(auth, staff_user_id=other.id, username=other.username, role="owner")
            # Independently verify personal scoping for two explicitly allowed users.
            monkeypatch.setattr(settings, "CALL_RECORDINGS_PILOT_STAFF_IDS", [actor.staff_user_id, other.id])
        response = await client.get(f"/api/manager/call-recordings/{recording_id}")
        assert response.status_code == 404 and "Дослать фото" not in response.text
        assert (await client.post(url, json=payload)).status_code == 404


@pytest.mark.asyncio
async def test_oauth_one_use_state_live_auth_version_and_current_demo_guard(context):
    factory, actor, provider = context
    auth = AuthenticatedUser(username=actor.username, auth_source="staff", staff_user_id=actor.staff_user_id, role="manager", tenant_id=1, storefront_id=1, auth_version=1)
    request = SimpleNamespace(session={})
    state = call_drive_oauth.start(request, auth, "http://test/callback")
    assert call_drive_oauth.consume(request, "wrong-state") is None
    pending = call_drive_oauth.consume(request, state)
    assert pending and call_drive_oauth.consume(request, state) is None
    async with factory() as session:
        assert (await call_drive_oauth.pending_actor(session, pending)).staff_user_id == actor.staff_user_id
        user = await session.get(StaffUser, actor.staff_user_id)
        user.auth_version += 1
        session.add(user)
        await session.commit()
        with pytest.raises(PermissionError):
            await call_drive_oauth.pending_actor(session, pending)
        tenant = await session.get(Tenant, 1)
        tenant.demo_read_only = True
        session.add(tenant)
        await session.commit()
        with pytest.raises(PermissionError, match="чтения"):
            await CallRecordingService.poll(session, actor, provider=provider)


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,payload", [
    ("GET", "/connection", None),
    ("GET", "", None),
    ("GET", "/1", None),
    ("GET", "/authorization-url", None),
    ("PUT", "/connection/folder", {"folder_id": "chosen-folder-00000001"}),
    ("DELETE", "/connection", None),
    ("POST", "/poll", {}),
    ("PATCH", "/1/metadata", {"expected_version": 1}),
    ("POST", "/1/retry", {"expected_version": 1}),
    ("POST", "/1/proposals/1/adopt", {"expected_version": 1, "task": {"text": "Пример поручения"}}),
])
async def test_private_pilot_revocation_blocks_every_authenticated_route(context, monkeypatch, method, path, payload):
    factory, actor, provider = context
    auth = AuthenticatedUser(username=actor.username, auth_source="staff", staff_user_id=actor.staff_user_id, role="owner", tenant_id=1, storefront_id=1, auth_version=1, is_system_tenant=True)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_manager_access] = lambda: auth
    async def sessions():
        async with factory() as session:
            yield session
    app.dependency_overrides[get_session] = sessions
    monkeypatch.setattr(settings, "CALL_RECORDINGS_PILOT_STAFF_IDS", [])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.request(method, "/api/manager/call-recordings" + path, **({"json": payload} if payload is not None else {}))
    assert response.status_code == 403 and "закрытого пилота" in response.text
    assert provider.downloads == 0


@pytest.mark.asyncio
async def test_pending_oauth_is_denied_after_pilot_access_is_revoked(context, monkeypatch):
    factory, actor, provider = context
    auth = AuthenticatedUser(username=actor.username, auth_source="staff", staff_user_id=actor.staff_user_id, role="manager", tenant_id=1, storefront_id=1, auth_version=1)
    request = SimpleNamespace(session={})
    state = call_drive_oauth.start(request, auth, "http://test/callback")
    pending = call_drive_oauth.consume(request, state)
    monkeypatch.setattr(settings, "CALL_RECORDINGS_PILOT_STAFF_IDS", [])
    async with factory() as session:
        with pytest.raises(PermissionError, match="закрытого пилота"):
            await call_drive_oauth.pending_actor(session, pending)
