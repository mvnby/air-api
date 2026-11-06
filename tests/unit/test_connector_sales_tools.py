"""Sales permissions and optional UI over the actual MCP HTTP transport."""

import pytest
from fastapi import HTTPException

from services.connector_mcp_tools import TOOLS
from services.connector_sales_ui import SALES_UI_URI
from tests.unit.test_connector_mcp_transport import mcp_client, _rpc


_SAVE = {"product_id": 1, "customer_id": 1, "installation": {},
         "expected_calculation_fingerprint": "a" * 64, "request_text": "Equipment with installation",
         "idempotency_key": "sales-scope-check-0001"}
_CUSTOMER = {"customer": {"type": "individual", "name": "Test customer"},
             "idempotency_key": "customer-scope-check-0001"}


def test_sales_discovery_exposes_precise_permissions_and_optional_final_views():
    save = TOOLS["save_sales_order"].definition().model_dump(by_alias=True)
    assert save["_meta"]["securitySchemes"][0]["scopes"] == [
        "kitlane:read", "kitlane:orders:write", "kitlane:catalog:write",
    ]
    assert save["annotations"]["readOnlyHint"] is False
    assert "ui" not in save["_meta"]
    customer = TOOLS["create_sales_customer"].definition().model_dump(by_alias=True)
    assert customer["_meta"]["securitySchemes"][0]["scopes"] == [
        "kitlane:read", "kitlane:customers:write",
    ]
    for name in ("select_sales_installation_options", "get_sales_order", "get_sales_order_offer"):
        definition = TOOLS[name].definition().model_dump(by_alias=True)
        assert definition["_meta"]["ui"]["resourceUri"] == SALES_UI_URI
        assert definition["annotations"]["readOnlyHint"] is True


@pytest.mark.asyncio
async def test_sales_save_requires_both_grants_before_dispatch(mcp_client, monkeypatch):
    client, access, checks, _ = mcp_client
    calls = []

    async def execute(*args, **kwargs):
        calls.append(True)
        raise LookupError("Reached domain")

    monkeypatch.setattr("services.connector_mcp.execute_tool", execute)
    access["token-one"].add("kitlane:orders:write")
    result = (await _rpc(client, "tools/call", {"name": "save_sales_order", "arguments": _SAVE})).json()["result"]
    assert result["structuredContent"]["error"]["code"] == "insufficient_scope"
    assert checks[-1] == ("token-one", "kitlane:catalog:write")
    assert calls == []
    access["token-one"].add("kitlane:catalog:write")
    result = (await _rpc(client, "tools/call", {"name": "save_sales_order", "arguments": _SAVE})).json()["result"]
    assert result["structuredContent"]["error"]["code"] == "not_found"
    assert calls == [True]
    result = (await _rpc(client, "tools/call", {"name": "create_sales_customer", "arguments": _CUSTOMER})).json()["result"]
    assert result["structuredContent"]["error"]["code"] == "insufficient_scope"
    assert checks[-1] == ("token-one", "kitlane:customers:write")
    assert calls == [True]


@pytest.mark.asyncio
async def test_sales_errors_preserve_actionable_public_fields_only(mcp_client, monkeypatch):
    client, access, _, _ = mcp_client
    access["token-one"].add("kitlane:customers:write")

    async def execute(*args, **kwargs):
        raise HTTPException(409, {"code": "customer_already_exists", "customer_id": 42,
                                  "matched_fields": ["phone"], "internal": "do not expose"})

    monkeypatch.setattr("services.connector_mcp.execute_tool", execute)
    result = (await _rpc(client, "tools/call", {"name": "create_sales_customer", "arguments": _CUSTOMER})).json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["customer_id"] == 42
    assert result["structuredContent"]["matched_fields"] == ["phone"]
    assert "internal" not in result["structuredContent"]


@pytest.mark.asyncio
async def test_sales_resource_mime_metadata_allowlist_and_revocation(mcp_client):
    client, access, _, _ = mcp_client
    listed = (await _rpc(client, "resources/list")).json()["result"]["resources"]
    assert len(listed) == 1 and listed[0]["uri"] == SALES_UI_URI
    response = await _rpc(client, "resources/read", {"uri": SALES_UI_URI})
    content = response.json()["result"]["contents"][0]
    assert content["mimeType"] == "text/html;profile=mcp-app"
    assert "ui/initialize" in content["text"]
    assert content["_meta"]["ui"]["csp"]["connectDomains"] == []
    invalid = await _rpc(client, "resources/read", {"uri": "file:///etc/passwd"})
    assert "error" in invalid.json()
    access.pop("token-one")
    revoked = await _rpc(client, "resources/read", {"uri": SALES_UI_URI})
    assert revoked.status_code == 401
