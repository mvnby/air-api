"""Multi-site tools use the same commands as Manager and respect OAuth grants."""

from types import SimpleNamespace

import pytest

from schemas_order_sites import OrderSiteItem, OrderSiteList
from services.connector_mcp_tools import TOOLS
from services.order_site_service import OrderSiteService, OrderSiteVersionConflict
from tests.unit.test_connector_mcp_transport import _rpc, mcp_client


@pytest.mark.parametrize("name", ["list_order_sites", "list_site_equipment"])
def test_site_reads_publish_bounded_read_only_contract(name):
    tool = TOOLS[name].definition()
    assert tool.annotations.readOnlyHint
    assert tool.meta["securitySchemes"][0]["scopes"] == ["kitlane:read"]
    assert tool.inputSchema["properties"]["limit"]["maximum"] == 100
    assert "order_id" in tool.inputSchema["required"]
    if name == "list_site_equipment":
        assert "site_id" in tool.inputSchema["required"]


@pytest.mark.parametrize("name", ["add_or_link_order_site", "link_order_equipment_to_site"])
def test_site_writes_publish_scoped_idempotent_contract(name):
    tool = TOOLS[name].definition()
    assert not tool.annotations.readOnlyHint
    assert tool.annotations.idempotentHint
    assert tool.meta["securitySchemes"][0]["scopes"] == ["kitlane:read", "kitlane:orders:write"]
    required = {"order_id", "idempotency_key", "payload"}
    if name == "link_order_equipment_to_site":
        required.add("site_id")
        assert "expected_version" in tool.inputSchema["$defs"]["OrderSiteEquipmentLinkPayload"]["required"]
    assert required <= set(tool.inputSchema["required"])
    assert not tool.inputSchema["additionalProperties"]


@pytest.mark.asyncio
async def test_connector_site_calls_keep_saved_ids_and_order_permissions(mcp_client, monkeypatch):
    client, access, _, _ = mcp_client
    site = OrderSiteItem(id=11, order_id=7, customer_branch_id=9,
        title="Цех A", address="Тестовый адрес, 1", version=1,
        manager_url="https://example.test/orders/7?section=work&orderSiteId=11#order-workspace-sites")
    calls = []

    async def list_sites(session, actor, order_id, *, limit, offset):
        assert actor.staff_user_id == 2 and order_id == 7
        return OrderSiteList(items=[site], total=1, limit=limit, offset=offset, legacy_primary=None)

    async def add_site(session, actor, order_id, payload, *, idempotency_key):
        calls.append((actor.staff_user_id, order_id, payload.customer_branch_id, idempotency_key))
        return SimpleNamespace(value=site, replayed=True)

    monkeypatch.setattr(OrderSiteService, "list_sites", list_sites)
    monkeypatch.setattr(OrderSiteService, "add_site", add_site)
    result = (await _rpc(client, "tools/call", {
        "name": "list_order_sites", "arguments": {"order_id": 7, "limit": 10},
    }, token="token-two")).json()["result"]
    assert not result["isError"]
    assert result["structuredContent"]["items"][0]["id"] == 11

    arguments = {"order_id": 7, "idempotency_key": "order-site-test-0001", "payload": {"customer_branch_id": 9}}
    request = {"name": "add_or_link_order_site", "arguments": arguments}
    denied = (await _rpc(client, "tools/call", request, token="token-two")).json()["result"]
    assert denied["isError"]
    assert denied["structuredContent"]["error"]["code"] == "insufficient_scope"
    assert not calls

    access["token-two"].add("kitlane:orders:write")
    result = (await _rpc(client, "tools/call", request, token="token-two")).json()["result"]
    assert not result["isError"]
    assert result["structuredContent"] == {"result": site.model_dump(mode="json"), "replayed": True}
    assert calls == [(2, 7, 9, "order-site-test-0001")]


@pytest.mark.asyncio
async def test_connector_equipment_link_returns_version_conflict(mcp_client, monkeypatch):
    client, access, _, _ = mcp_client
    access["token-one"].add("kitlane:orders:write")

    async def link_equipment(session, actor, order_id, site_id, payload, *, idempotency_key):
        assert actor.staff_user_id == 1
        assert (order_id, site_id, payload.equipment_id, payload.expected_version) == (7, 11, 33, 1)
        raise OrderSiteVersionConflict()

    monkeypatch.setattr(OrderSiteService, "link_equipment", link_equipment)
    result = (await _rpc(client, "tools/call", {
        "name": "link_order_equipment_to_site",
        "arguments": {"order_id": 7, "site_id": 11, "idempotency_key": "order-site-test-0002",
                      "payload": {"equipment_id": 33, "expected_version": 1}},
    })).json()["result"]
    assert result["isError"]
    assert result["structuredContent"]["error"]["code"] == "version_conflict"
