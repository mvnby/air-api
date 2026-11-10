"""Equipment MCP contract and OAuth permission boundary."""

from types import SimpleNamespace

import pytest

from schemas_order_equipment_identity import OrderEquipmentIdentity, OrderEquipmentSaveResult, OrderEquipmentState
from services.connector_mcp_tools import TOOLS
from services.order_equipment_identity_service import OrderEquipmentIdentityService
from tests.unit.test_connector_mcp_transport import mcp_client, _rpc


def test_equipment_tools_publish_shared_versioned_contracts():
    read, write = TOOLS["get_order_equipment"].definition(), TOOLS["save_order_equipment"].definition()
    assert read.annotations.readOnlyHint and not write.annotations.readOnlyHint
    assert write.annotations.idempotentHint
    assert write.meta["securitySchemes"][0]["scopes"] == ["kitlane:read", "kitlane:orders:write"]
    assert {"expected_version", "idempotency_key", "order_id"} <= set(write.inputSchema["required"])
    assert {"equipment_id", "source_document_id", "expected_equipment_version"} <= write.inputSchema["properties"].keys()
    assert write.inputSchema["additionalProperties"] is False


def test_consumer_document_discovery_is_bounded_read_only_metadata():
    tool = TOOLS["list_order_consumer_documents"].definition()
    assert tool.annotations.readOnlyHint
    assert tool.meta["securitySchemes"][0]["scopes"] == ["kitlane:read"]
    assert tool.inputSchema["properties"]["limit"]["maximum"] == 100
    from schemas_connector_service_order_document import ConsumerDocumentSummary
    assert not {"render_snapshot", "artifacts", "equipment_serial"} & ConsumerDocumentSummary.model_fields.keys()


@pytest.mark.asyncio
async def test_equipment_tools_require_order_write_and_keep_saved_identity(mcp_client, monkeypatch):
    client, access, checks, _ = mcp_client
    identity = OrderEquipmentIdentity(equipment_id=17, version="equipment-v1", customer_id=5,
        customer_branch_id=None, catalog_product_id=None, equipment_source="customer_owned",
        brand="TEST", model="TEST-09", serial="TEST-SN-001", roles=["installation"])
    state = OrderEquipmentState(order_id=9, version="order-v1", items=[identity], total=1,
                               manager_url="https://example.test/orders/9")
    writes = []

    async def read(session, actor, order_id, **kwargs):
        assert actor.staff_user_id == 1 and order_id == 9
        return state

    async def save(session, actor, data):
        writes.append(data)
        return SimpleNamespace(value=OrderEquipmentSaveResult(order_id=9, equipment_id=17,
            version="order-v1", equipment=identity, manager_url=state.manager_url), replayed=True)

    monkeypatch.setattr(OrderEquipmentIdentityService, "read", read)
    monkeypatch.setattr(OrderEquipmentIdentityService, "save", save)
    read_result = (await _rpc(client, "tools/call", {"name": "get_order_equipment", "arguments": {"order_id": 9}})).json()["result"]
    assert not read_result["isError"]
    assert read_result["structuredContent"]["items"][0]["serial"] == "TEST-SN-001"
    args = {"order_id": 9, "expected_version": "order-v1", "idempotency_key": "equipment-scope-0001", "equipment_id": 17}
    denied = (await _rpc(client, "tools/call", {"name": "save_order_equipment", "arguments": args})).json()["result"]
    assert denied["isError"] and denied["structuredContent"]["error"]["code"] == "insufficient_scope"
    assert not writes
    access["token-one"].add("kitlane:orders:write")
    result = (await _rpc(client, "tools/call", {"name": "save_order_equipment", "arguments": args})).json()["result"]
    assert not result["isError"]
    assert result["structuredContent"]["result"]["equipment_id"] == 17
    assert result["structuredContent"]["replayed"] is True
    assert writes[0].equipment_id == 17 and "model" not in writes[0].model_fields_set
