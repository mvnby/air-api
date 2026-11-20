"""The three-site order can be saved and reopened through live MCP grants."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from models import Customer, CustomerBranch, CustomerEquipment, Order, OrderStatus
from tests.integration.test_connector_mcp_maintenance import call, client_for, grant, success


@pytest.mark.asyncio
async def test_mcp_order_sites_and_equipment_are_persistent_and_replay_safe(db_engine):
    async with AsyncSession(db_engine, expire_on_commit=False) as db:
        customer = Customer(tenant_id=1, name="Test multi-site customer", phone="")
        db.add(customer)
        await db.flush()
        primary = CustomerBranch(customer_id=customer.id, name="A", delivery_address="Test address A")
        secondary = CustomerBranch(customer_id=customer.id, name="B", delivery_address="Test address B")
        db.add_all([primary, secondary])
        await db.flush()
        order = Order(tenant_id=1, storefront_id=1, customer_id=customer.id,
            customer_branch_id=primary.id, status=OrderStatus.NEGOTIATION, workflow_type="service_work")
        existing = CustomerEquipment(customer_id=customer.id, customer_branch_id=secondary.id,
            display_name="Existing split")
        db.add_all([order, existing])
        await db.commit()
        token, *_ = await grant(db, scopes="kitlane:read kitlane:orders:write")
        order_args = {"order_id": order.id}

        async with client_for(db, token) as client:
            initial = success(await call(client, "list_order_sites", order_args))
            assert initial["legacy_primary"]["customer_branch_id"] == primary.id

            async def add_site(key, payload):
                return success(await call(client, "add_or_link_order_site", {
                    **order_args, "idempotency_key": key, "payload": payload,
                }))

            a = (await add_site("mcp-site-test-add-a", {"customer_branch_id": primary.id}))["result"]
            b = (await add_site("mcp-site-test-add-b", {"customer_branch_id": secondary.id}))["result"]
            c_payload = {"title": "C", "address": "Test address C"}
            c = (await add_site("mcp-site-test-add-c", c_payload))["result"]
            assert await add_site("mcp-site-test-add-c", c_payload) == {"result": c, "replayed": True}

            def args_for(site, key, **payload):
                return {**order_args, "site_id": site["id"], "idempotency_key": key,
                    "payload": {"expected_version": site["version"], **payload}}

            async def link_unit(arguments):
                return success(await call(client, "link_order_equipment_to_site", arguments))

            a_args = args_for(a, "mcp-site-unit-test-a", equipment={"display_name": "Unit A"})
            saved = await link_unit(a_args)
            assert (await link_unit(a_args)) == {**saved, "replayed": True}
            stale = await call(client, "link_order_equipment_to_site", {
                **a_args, "idempotency_key": "mcp-site-unit-test-stale",
            })
            assert stale["isError"]
            assert stale["structuredContent"]["error"]["code"] == "version_conflict"

            b_saved = await link_unit(args_for(b, "mcp-site-unit-test-b1", equipment_id=existing.id))
            await link_unit(args_for(b_saved["result"]["site"], "mcp-site-unit-test-b2",
                equipment={"display_name": "Unit B2 with unknown model"}))
            await link_unit(args_for(c, "mcp-site-unit-test-c", equipment={
                "display_name": "Unit C",
                "components": [{"component_type": "drain_pump", "title": "Drain pump"}],
            }))

        async with client_for(db, token) as reopened:
            sites = success(await call(reopened, "list_order_sites", order_args))
            assert {item["id"] for item in sites["items"]} == {a["id"], b["id"], c["id"]}
            for site, expected in [(a, 1), (b, 2), (c, 1)]:
                page = success(await call(reopened, "list_site_equipment", {**order_args, "site_id": site["id"]}))
                assert page["total"] == expected
                assert {item["site_id"] for item in page["items"]} == {site["id"]}
                if site is c:
                    assert page["items"][0]["equipment"]["components"][0]["component_type"] == "drain_pump"

        assert await db.scalar(select(func.count()).select_from(Order)) == 1
        await db.refresh(order)
        assert order.customer_branch_id == primary.id
