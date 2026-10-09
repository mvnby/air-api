"""Real SDK transport checks with isolated application-service substitutes."""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
from starlette.applications import Starlette
from starlette.routing import Route

from core.command_actor import CommandActor
from models.tenancy import TenantScope
from schemas_incoming import IncomingListResponse, IncomingResponse
from services.connector_auth_policy import ConnectorAuthError
from services.connector_auth_service import ConnectorAuthService
from services.connector_mcp import ConnectorMCPApplication
from services.incoming_command_service import IncomingCommandService


@asynccontextmanager
async def _sessions():
    yield SimpleNamespace()


@pytest.fixture
async def mcp_client(monkeypatch):
    access = {"token-one": {"kitlane:read", "kitlane:incoming:write", "kitlane:tasks:write"},
              "token-two": {"kitlane:read"}}
    checks = []

    async def resolve(session, token, required_scope):
        checks.append((token, required_scope))
        if token not in access:
            raise ConnectorAuthError("invalid_token", "Connection revoked", 401)
        if required_scope not in access[token]:
            raise ConnectorAuthError("insufficient_scope", "Required scope missing", 403)
        user = 1 if token == "token-one" else 2
        return CommandActor(user, f"user-{user}", TenantScope(user, user), "chatgpt")

    monkeypatch.setattr(ConnectorAuthService, "resolve_actor", resolve)
    adapter = ConnectorMCPApplication(session_factory=_sessions)

    @asynccontextmanager
    async def lifespan(app):
        async with adapter.lifespan():
            yield

    app = Starlette(routes=[Route("/api/connector/mcp", adapter, methods=["GET", "POST", "DELETE"])], lifespan=lifespan)
    # pytest-asyncio may finalize an async fixture in a different Task. ASGI
    # lifespan must enter/exit its AnyIO cancel scope in the same owning Task.
    ready, stop = asyncio.Event(), asyncio.Event()

    async def run_lifespan():
        async with app.router.lifespan_context(app):
            ready.set()
            await stop.wait()

    lifecycle = asyncio.create_task(run_lifespan())
    await ready.wait()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://api.mvn.by", headers={
            "Authorization": "Bearer token-one", "Accept": "application/json, text/event-stream",
        }) as client:
            yield client, access, checks, adapter
    finally:
        stop.set()
        await lifecycle


async def _rpc(client, method, params=None, *, token="token-one", request_id=1):
    body = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        body["params"] = params
    return await client.post("/api/connector/mcp", json=body, headers={"Authorization": f"Bearer {token}"})


@pytest.mark.asyncio
async def test_incoming_explicit_clarification_requires_task_scope_before_mutation(mcp_client, monkeypatch):
    client, access, checks, _ = mcp_client
    access["token-two"].add("kitlane:incoming:write")
    mutated = []
    async def create(*args, **kwargs):
        mutated.append(True)
        raise LookupError("test mutation reached")
    monkeypatch.setattr(IncomingCommandService, "create", create)
    arguments = {"idempotency_key": "clarification-scope-0001", "payload": {"request_text": "ТО квартиры; адрес уточнить"}}
    denied = await _rpc(client, "tools/call", {"name": "create_incoming", "arguments": arguments}, token="token-two")
    result = denied.json()["result"]
    assert result["isError"] and result["structuredContent"]["error"]["code"] == "insufficient_scope"
    assert not mutated
    assert "kitlane:tasks:write" in str(result)
    assert checks[-1] == ("token-two", "kitlane:tasks:write")
    arguments["payload"]["clarification_requested"] = False
    allowed_intake = await _rpc(client, "tools/call", {"name": "create_incoming", "arguments": arguments}, token="token-two")
    assert allowed_intake.json()["result"]["structuredContent"]["error"]["code"] == "not_found"
    assert mutated == [True]


@pytest.mark.asyncio
async def test_real_sdk_handshake_discovery_and_actor_isolation(mcp_client):
    client, access, checks, adapter = mcp_client
    initialize = await _rpc(client, "initialize", {
        "protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"},
    })
    assert initialize.status_code == 200
    assert initialize.json()["result"]["serverInfo"]["name"] == "kitlane"
    assert "mcp-session-id" not in initialize.headers
    initialized = await client.post("/api/connector/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert initialized.status_code == 202
    discovery = await _rpc(client, "tools/list")
    tools = {tool["name"]: tool for tool in discovery.json()["result"]["tools"]}
    assert {"create_incoming", "create_task", "get_order", "complete_task"} <= tools.keys()
    assert tools["get_order"]["annotations"]["readOnlyHint"] is True
    assert tools["create_incoming"]["annotations"]["readOnlyHint"] is False
    assert tools["update_task"]["annotations"]["destructiveHint"] is True
    assert tools["create_task"]["outputSchema"]["type"] == "object"
    assert tools["create_task"]["_meta"]["securitySchemes"][0]["scopes"] == ["kitlane:read", "kitlane:tasks:write"]
    for tool in tools.values():
        assert "actor" not in tool["inputSchema"].get("properties", {})
        assert "tenant_id" not in tool["inputSchema"].get("properties", {})
        assert tool["annotations"]["openWorldHint"] is False
    first = (await _rpc(client, "tools/call", {"name": "get_current_context", "arguments": {}})).json()["result"]
    second = (await _rpc(client, "tools/call", {"name": "get_current_context", "arguments": {}}, token="token-two")).json()["result"]
    assert not first["isError"] and not second["isError"]
    assert first["structuredContent"]["staff_user_id"] == 1
    assert second["structuredContent"]["staff_user_id"] == 2
    assert first["structuredContent"]["tenant_id"] != second["structuredContent"]["tenant_id"]
    assert checks.count(("token-one", "kitlane:read")) >= 4


@pytest.mark.asyncio
async def test_revocation_after_initialization_and_scope_downgrade(mcp_client, monkeypatch):
    client, access, checks, adapter = mcp_client
    initialized = await _rpc(client, "initialize", {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}})
    assert initialized.status_code == 200
    access["token-one"] = {"kitlane:read"}
    write = await _rpc(client, "tools/call", {"name": "create_incoming", "arguments": {
        "idempotency_key": "request-123456789", "payload": {"request_text": "Нужен кондиционер"},
    }})
    assert write.json()["result"]["isError"] is True
    assert write.json()["result"]["structuredContent"]["error"]["code"] == "insufficient_scope"
    assert "mcp/www_authenticate" in write.json()["result"]["_meta"]
    assert 'scope="kitlane:read kitlane:incoming:write"' in write.json()["result"]["_meta"]["mcp/www_authenticate"][0]
    del access["token-one"]
    revoked = await _rpc(client, "tools/call", {"name": "get_current_context", "arguments": {}})
    assert revoked.status_code == 401
    assert "resource_metadata=" in revoked.headers["www-authenticate"]


@pytest.mark.asyncio
async def test_backend_write_retry_and_extra_fields_are_rejected(mcp_client, monkeypatch):
    client, access, checks, adapter = mcp_client
    receipts = {}
    writes = []

    async def create(session, *, actor, payload, idempotency_key):
        assert actor.staff_user_id == 1 and actor.channel == "chatgpt"
        writes.append((idempotency_key, payload.model_dump()))
        replayed = idempotency_key in receipts
        if not replayed:
            receipts[idempotency_key] = IncomingResponse(
                lead_id=42, version=1, request_text=payload.request_text,
                original_text=payload.request_text,
                intake_state="needs_contact", missing_fields=["contact", "address"],
                source_occurred_at=datetime.now(timezone.utc), source_timezone="Europe/Minsk",
                manager_url="https://api.mvn.by/manager/leads?incomingId=42",
            )
        return SimpleNamespace(value=receipts[idempotency_key], replayed=replayed)

    monkeypatch.setattr(IncomingCommandService, "create", create)
    args = {"idempotency_key": "incoming-1234567890", "payload": {"request_text": "Клиент хочет монтаж завтра"}}
    first = (await _rpc(client, "tools/call", {"name": "create_incoming", "arguments": args})).json()["result"]
    retry = (await _rpc(client, "tools/call", {"name": "create_incoming", "arguments": args})).json()["result"]
    assert not first["isError"] and not retry["isError"], (first, retry)
    assert first["structuredContent"]["result"]["lead_id"] == 42
    assert retry["structuredContent"]["replayed"] is True
    assert first["structuredContent"]["result"] == retry["structuredContent"]["result"]
    assert writes[0] == writes[1]
    forged = (await _rpc(client, "tools/call", {"name": "create_incoming", "arguments": {**args, "actor": {"tenant_id": 999}}})).json()["result"]
    assert forged["isError"] is True
    assert len(writes) == 2


@pytest.mark.asyncio
async def test_unauthenticated_and_unexpected_errors_do_not_expose_details(mcp_client, monkeypatch):
    client, access, checks, adapter = mcp_client
    unauth = await client.post("/api/connector/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers={"Authorization": ""})
    assert unauth.status_code == 401
    async def fail(*args):
        raise RuntimeError("private-token-value and customer source text")

    monkeypatch.setattr("services.connector_mcp.execute_tool", fail)
    response = await _rpc(client, "tools/call", {"name": "get_current_context", "arguments": {}})
    assert response.json()["result"]["isError"] is True
    assert "private-token-value" not in response.text


@pytest.mark.asyncio
async def test_current_versions_timezone_dates_and_pagination_are_required(mcp_client):
    client, _, _, _ = mcp_client
    cases = [
        ("complete_task", {"idempotency_key": "complete-12345678", "task_id": 1}),
        ("create_task", {"idempotency_key": "task-123456789012", "payload": {"text": "Позвонить", "due_at": "2026-10-06T12:00:00"}}),
        ("list_tasks", {"limit": 1000}),
        ("search_customers", {"query": "Иван", "limit": 1000}),
        ("search_customers", {"query": "   "}),
    ]
    for name, args in cases:
        response = await _rpc(client, "tools/call", {"name": name, "arguments": args})
        assert response.json()["result"]["isError"] is True


@pytest.mark.asyncio
async def test_transport_rejects_foreign_origin(mcp_client):
    client, _, _, _ = mcp_client
    response = await client.post("/api/connector/mcp", headers={"Origin": "https://evil.example"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_tool_pagination_defaults_reach_application_service(mcp_client, monkeypatch):
    client, _, _, _ = mcp_client
    observed = []

    async def list_incoming(session, *, actor, limit, offset):
        observed.append((limit, offset))
        return IncomingListResponse(items=[], total=0)

    monkeypatch.setattr(IncomingCommandService, "list", list_incoming)
    response = await _rpc(client, "tools/call", {"name": "list_incoming", "arguments": {}})
    assert not response.json()["result"]["isError"]
    assert observed == [(10, 0)]


@pytest.mark.asyncio
async def test_maximum_escaped_unicode_is_accepted_with_finite_body_limit(mcp_client, monkeypatch):
    client, _, _, _ = mcp_client
    text = "🙂" * 12000
    calls = []

    async def execute(session, actor, tool, arguments):
        assert arguments["payload"]["request_text"] == text
        calls.append(tool.name)
        result = IncomingResponse(lead_id=42, version=1, request_text=text, original_text=text,
            intake_state="needs_contact", missing_fields=["contact", "address"],
            source_occurred_at=None, source_timezone="Europe/Minsk",
            manager_url="https://api.mvn.by/manager/leads?incomingId=42")
        return {"result": result.model_dump(mode="json"), "replayed": False}

    monkeypatch.setattr("services.connector_mcp.execute_tool", execute)
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "create_incoming", "arguments": {"idempotency_key": "unicode-transport-0001", "payload": {"request_text": text}},
    }}, ensure_ascii=True).encode()
    assert len(body) > 96 * 1024
    accepted = await client.post("/api/connector/mcp", content=body, headers={"Content-Type": "application/json"})
    assert accepted.status_code == 200
    assert not accepted.json()["result"]["isError"]
    oversized = await client.post("/api/connector/mcp", content=body + b" " * (512 * 1024), headers={"Content-Type": "application/json"})
    assert oversized.status_code == 413
    assert calls == ["create_incoming"]


@pytest.mark.asyncio
async def test_maximum_escaped_maintenance_fields_fit_the_finite_transport(mcp_client, monkeypatch):
    from schemas_connector_maintenance import ConnectorFindingResult
    client, access, _, _ = mcp_client
    access['token-one'].add('kitlane:maintenance:write')
    text = '🙂' * 10000
    arguments = {'order_id': 1, 'idempotency_key': 'maintenance-unicode-0001', 'payload': {
        'original_comment': text, 'facts': text, 'recommendation': text, 'equipment_description': '🙂' * 2000,
        'observed_at': '2026-10-09T10:00:00+03:00'}}
    calls = []
    async def execute(session, actor, tool, values):
        inputs = tool.input_model.model_validate(values)
        calls.append(tool.name)
        now = datetime.now(timezone.utc)
        item = ConnectorFindingResult(**inputs.payload.model_dump(), id=1, source_order_id=1, customer_id=1,
            customer_branch_id=None, origin='chatgpt_maintenance', created_at=now, updated_at=now,
            created_by='user-1', updated_by='user-1', version=1, manager_url='https://api.mvn.by/manager')
        return {'result': item.model_dump(mode='json'), 'replayed': False}
    monkeypatch.setattr('services.connector_mcp.execute_tool', execute)
    body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {
        'name': 'create_maintenance_finding', 'arguments': arguments}}, ensure_ascii=True).encode()
    assert 256 * 1024 < len(body) < 512 * 1024
    accepted = await client.post('/api/connector/mcp', content=body, headers={'Content-Type': 'application/json'})
    assert accepted.status_code == 200 and not accepted.json()['result']['isError']
    assert calls == ['create_maintenance_finding']
