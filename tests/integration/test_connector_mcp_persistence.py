"""MCP protocol through real OAuth, shared commands and PostgreSQL persistence."""

from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from sqlalchemy import func
from sqlmodel import select
from starlette.applications import Starlette
from starlette.routing import Route

from core.security import AuthenticatedUser
from models import Lead, StaffUser
from models.command_audit import CommandAuditEvent
from models.personal_task import PersonalTask
from models.tenancy import TenantMembership
from services.connector_auth_policy import CLIENT_ID, pkce, resource
from services.connector_auth_service import ConnectorAuthService
from services.connector_mcp import ConnectorMCPApplication


@pytest.mark.asyncio
async def test_mcp_real_commands_retries_versions_and_live_role_revocation(db):
    user = StaffUser(display_name="MCP owner", username="mcp-owner", primary_role="admin", roles=["admin"])
    db.add(user)
    await db.flush()
    membership = TenantMembership(tenant_id=1, staff_user_id=user.id, role="admin")
    db.add(membership)
    await db.commit()
    auth = AuthenticatedUser(username=user.username, auth_source="staff", staff_user_id=user.id,
        role="admin", tenant_id=1, storefront_id=1, tenant_membership_id=membership.id,
        is_system_tenant=True, auth_version=1)
    verifier = "m" * 64
    redirect = "https://chatgpt.com/connector_platform_oauth_redirect"
    pending, nonce = await ConnectorAuthService.start_consent(db, auth, "manager-session", client_id=CLIENT_ID,
        redirect_uri=redirect, requested_resource=resource(), scope="kitlane:read kitlane:incoming:write kitlane:tasks:write",
        state="mcp-state", code_challenge=pkce(verifier), code_challenge_method="S256", response_type="code")
    callback = await ConnectorAuthService.finish_consent(db, auth, "manager-session", consent_id=pending.id, nonce=nonce, allow=True)
    token = await ConnectorAuthService.exchange_code(db, code=parse_qs(urlsplit(callback).query)["code"][0],
        client_id=CLIENT_ID, redirect_uri=redirect, requested_resource=resource(), code_verifier=verifier)

    @asynccontextmanager
    async def session_factory():
        yield db

    adapter = ConnectorMCPApplication(session_factory=session_factory)
    app = Starlette(routes=[Route("/api/connector/mcp", adapter, methods=["GET", "POST", "DELETE"])])
    async with adapter.lifespan():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://api.mvn.by", headers={
            "Authorization": f"Bearer {token.access_token}", "Accept": "application/json, text/event-stream",
        }) as client:
            async def rpc(method, params=None):
                payload = {"jsonrpc": "2.0", "id": 1, "method": method}
                if params is not None:
                    payload["params"] = params
                return await client.post("/api/connector/mcp", json=payload)

            async def call(name, arguments):
                response = await rpc("tools/call", {"name": name, "arguments": arguments})
                assert response.status_code == 200
                return response.json()["result"]

            init = await rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}})
            assert init.status_code == 200
            incoming_args = {"idempotency_key": "mcp-incoming-create-0001", "payload": {
                "request_text": "  Клиент хочет кондиционер. Адрес ещё неизвестен.  ",
                "source_occurred_at": "2026-10-06T09:00:00+03:00", "source_timezone": "Europe/Minsk",
            }}
            created = await call("create_incoming", incoming_args)
            assert not created["isError"], created
            replay = await call("create_incoming", incoming_args)
            assert replay["structuredContent"]["replayed"]
            incoming = created["structuredContent"]["result"]
            assert incoming["intake_state"] == "needs_contact"
            assert incoming["original_text"] == incoming_args["payload"]["request_text"]
            changed_args = {**incoming_args, "payload": {"request_text": "Другой запрос"}}
            conflict = await call("create_incoming", changed_args)
            assert conflict["isError"] and conflict["structuredContent"]["error"]["status"] == 409
            task_args = {"idempotency_key": "mcp-task-create-0001", "payload": {
                "text": "Уточнить адрес", "lead_id": incoming["lead_id"], "due_at": "2026-10-07T10:00:00+03:00",
            }}
            task_created = await call("create_task", task_args)
            assert not task_created["isError"], task_created
            task = task_created["structuredContent"]["result"]
            task_replay = await call("create_task", task_args)
            assert task_replay["structuredContent"]["replayed"]
            completed = await call("complete_task", {"task_id": task["id"], "expected_version": task["version"], "idempotency_key": "mcp-task-complete-0001"})
            assert not completed["isError"], completed
            assert completed["structuredContent"]["result"]["status"] == "completed"
            stale = await call("reopen_task", {"task_id": task["id"], "expected_version": task["version"], "idempotency_key": "mcp-task-reopen-stale1"})
            assert stale["structuredContent"]["error"]["status"] == 409
            read = await call("get_incoming", {"lead_id": incoming["lead_id"]})
            assert not read["isError"] and read["structuredContent"]["lead_id"] == incoming["lead_id"]
            assert (await db.execute(select(func.count()).select_from(Lead).where(Lead.intake_event_key.is_not(None)))).scalar_one() == 1
            assert (await db.execute(select(func.count()).select_from(PersonalTask))).scalar_one() == 1
            audits = (await db.execute(select(CommandAuditEvent).where(CommandAuditEvent.channel == "chatgpt"))).scalars().all()
            assert {row.operation for row in audits} == {"incoming.create", "personal_task.create", f"personal_task.complete.{task['id']}"}
            # The established MCP initialization cannot bypass a changed role.
            membership.role = "manager"
            await db.commit()
            rejected = await rpc("tools/call", {"name": "get_current_context", "arguments": {}})
            assert rejected.status_code == 401
