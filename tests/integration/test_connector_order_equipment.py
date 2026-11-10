"""Saved nameplate facts remain readable through real OAuth/MCP exchanges."""

from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from starlette.applications import Starlette
from starlette.routing import Route

from core.security import AuthenticatedUser
from models.tenancy import TenantMembership
from services.connector_auth_policy import CLIENT_ID, pkce, resource
from services.connector_auth_service import ConnectorAuthService
from services.connector_mcp import ConnectorMCPApplication
from tests.integration.test_order_equipment_identity import seed


@pytest.mark.asyncio
async def test_oauth_mcp_save_retry_and_reopen(db):
    actor, order = await seed(db)
    membership = TenantMembership(tenant_id=1, staff_user_id=actor.staff_user_id, role="admin")
    db.add(membership)
    await db.commit()
    auth = AuthenticatedUser(username=actor.username, auth_source="staff", staff_user_id=actor.staff_user_id,
        role="admin", tenant_id=1, storefront_id=1, tenant_membership_id=membership.id,
        is_system_tenant=True, auth_version=1)
    verifier, redirect = "e" * 64, "https://chatgpt.com/connector_platform_oauth_redirect"
    pending, nonce = await ConnectorAuthService.start_consent(db, auth, "equipment-test-session", client_id=CLIENT_ID,
        redirect_uri=redirect, requested_resource=resource(), scope="kitlane:read kitlane:orders:write",
        state="equipment-state", code_challenge=pkce(verifier), code_challenge_method="S256", response_type="code")
    callback = await ConnectorAuthService.finish_consent(db, auth, "equipment-test-session", consent_id=pending.id, nonce=nonce, allow=True)
    token = await ConnectorAuthService.exchange_code(db, code=parse_qs(urlsplit(callback).query)["code"][0],
        client_id=CLIENT_ID, redirect_uri=redirect, requested_resource=resource(), code_verifier=verifier)

    @asynccontextmanager
    async def sessions():
        yield db

    adapter = ConnectorMCPApplication(session_factory=sessions)
    app = Starlette(routes=[Route("/api/connector/mcp", adapter, methods=["GET", "POST", "DELETE"])])
    async with adapter.lifespan():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://api.mvn.by", headers={
            "Authorization": f"Bearer {token.access_token}", "Accept": "application/json, text/event-stream",
        }) as client:
            async def call(name, arguments):
                response = await client.post("/api/connector/mcp", json={"jsonrpc": "2.0", "id": 1,
                    "method": "tools/call", "params": {"name": name, "arguments": arguments}})
                assert response.status_code == 200
                return response.json()["result"]

            before = await call("get_order_equipment", {"order_id": order.id})
            assert not before["isError"], before
            args = {"order_id": order.id, "expected_version": before["structuredContent"]["version"],
                "idempotency_key": "equipment-mcp-create-0001", "brand": "TEST", "model": "TEST-09", "serial": "TEST-SN-001"}
            created = await call("save_order_equipment", args)
            assert not created["isError"], created
            repeat = await call("save_order_equipment", args)
            assert not repeat["isError"] and repeat["structuredContent"]["replayed"]
            saved = created["structuredContent"]["result"]
            reopened = await call("get_order_equipment", {"order_id": order.id})
            item = reopened["structuredContent"]["items"][0]
            assert item["equipment_id"] == saved["equipment_id"]
            assert item["model"] == "TEST-09" and item["serial"] == "TEST-SN-001"
            assert "/orders/" in saved["manager_url"]
