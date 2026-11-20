"""The same service order keeps three locations and all four physical systems."""

import asyncio

import pytest
from sqlalchemy import func
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select

from core.command_actor import CommandActor
from models import (
    Customer, CustomerBranch, CustomerEquipment, CustomerType, EquipmentOrderLink, Order, OrderStatus, StaffUser,
)
from models.order_site import OrderSite, OrderSiteEquipment
from models.tenancy import Storefront, Tenant, TenantMembership, TenantScope
from schemas_order_sites import OrderSiteAddPayload, OrderSiteEquipmentLinkPayload
from services.order_site_service import OrderSiteService, OrderSiteVersionConflict
from tests.integration.test_manager_access_permissions import _headers


async def make_workspace(db):
    user = StaffUser(username="sites-test-manager", display_name="Sites manager", primary_role="manager", roles=["manager"])
    customer = Customer(tenant_id=1, name="Тестовая сервисная организация", phone="", type=CustomerType.company)
    outsider = Customer(tenant_id=1, name="Другой тестовый заказчик", phone="", type=CustomerType.company)
    db.add_all([user, customer, outsider])
    await db.flush()
    db.add(TenantMembership(tenant_id=1, staff_user_id=user.id, role="manager"))
    branches = [CustomerBranch(customer_id=customer.id, name=f"Объект {name}", delivery_address=f"Тестовый адрес {name}")
                for name in ("А", "Б")]
    foreign_branch = CustomerBranch(customer_id=outsider.id, name="Другой объект", delivery_address="Тестовая площадка")
    db.add_all([*branches, foreign_branch])
    await db.flush()
    order = Order(
        tenant_id=1, storefront_id=1, customer_id=customer.id, customer_branch_id=branches[0].id,
        delivery_address="Основная площадка по заказу", workflow_type="service_work", status=OrderStatus.EXECUTION,
    )
    db.add(order)
    await db.commit()
    return user, customer, outsider, branches, foreign_branch, order


async def post_command(client, headers, path, key, payload):
    return await client.post(path, headers=headers, json={"idempotency_key": key, "payload": payload})


async def add_site(client, headers, path, key, payload):
    response = await post_command(client, headers, path, key, payload)
    assert response.status_code == 200, response.text
    return response.json()["result"]


@pytest.mark.asyncio
async def test_manager_three_sites_four_physical_units_and_legacy_primary(async_client, db):
    user, customer, _, branches, _, order = await make_workspace(db)
    headers = _headers(user)
    path = f"/api/manager/orders/{order.id}/sites"

    legacy = await async_client.get(path, headers=headers)
    assert legacy.status_code == 200, legacy.text
    assert legacy.json() == {"items": [], "total": 0, "limit": 100, "offset": 0, "legacy_primary": {
        "customer_branch_id": branches[0].id, "title": "Объект А", "address": "Основная площадка по заказу",
    }}
    assert await db.scalar(select(func.count()).select_from(OrderSite)) == 0

    site_a = await add_site(async_client, headers, path, "site-first-create-0001", {"customer_branch_id": branches[0].id})
    replay = await post_command(async_client, headers, path, "site-first-create-0001", {"customer_branch_id": branches[0].id})
    assert replay.json() == {"result": site_a, "replayed": True}
    duplicate = await add_site(async_client, headers, path, "site-first-create-0002", {"customer_branch_id": branches[0].id})
    assert duplicate == site_a

    site_b = await add_site(async_client, headers, path, "site-second-create-0001", {"customer_branch_id": branches[1].id})
    site_c = await add_site(async_client, headers, path, "site-third-create-0001", {"title": "Объект В", "address": "Тестовый адрес В"})
    assert len({site["id"] for site in (site_a, site_b, site_c)}) == 3

    registered = CustomerEquipment(customer_id=customer.id, customer_branch_id=branches[1].id, model="TEST-09")
    db.add(registered)
    await db.commit()

    async def add_unit(site, key, unit):
        result = await post_command(
            async_client, headers, f"{path}/{site['id']}/equipment", key,
            {**unit, "expected_version": site["version"]},
        )
        assert result.status_code == 200, result.text
        return result.json()["result"]

    unit_a = await add_unit(site_a, "unit-first-create-0001", {"equipment": {"display_name": "Настенная система"}})
    unit_b1 = await add_unit(site_b, "unit-second-attach-0001", {"equipment_id": registered.id})
    unit_b2 = await add_unit(unit_b1["site"], "unit-second-create-0001", {"equipment": {"model": "TEST-09"}})
    components = [{"component_type": kind, "model": model} for kind, model in (
        ("indoor_unit", "TEST-IN"), ("outdoor_unit", "TEST-OUT"), ("drain_pump", "TEST-PUMP"),
    )]
    unit_request = {"equipment": {"display_name": "Система с насосом", "components": components}}
    unit_c = await add_unit(site_c, "unit-third-create-0001", unit_request)
    unit_c_replay = await post_command(
        async_client, headers, f"{path}/{site_c['id']}/equipment", "unit-third-create-0001",
        {**unit_request, "expected_version": site_c["version"]},
    )
    assert unit_c_replay.json() == {"result": unit_c, "replayed": True}
    assert unit_a["equipment"]["equipment"]["serial"] is None
    assert unit_b1["equipment"]["equipment_id"] != unit_b2["equipment"]["equipment_id"]
    assert {part["component_type"] for part in unit_c["equipment"]["equipment"]["components"]} == {
        "indoor_unit", "outdoor_unit", "drain_pump",
    }

    for site, expected in ((site_a, 1), (site_b, 2), (site_c, 1)):
        response = await async_client.get(f"{path}/{site['id']}/equipment", headers=headers, params={"limit": 1})
        assert response.status_code == 200, response.text
        assert response.json()["total"] == expected
        assert len(response.json()["items"]) == 1
    assert await db.scalar(select(func.count()).select_from(CustomerEquipment)) == 4
    assert await db.scalar(select(func.count()).select_from(OrderSiteEquipment)) == 4
    assert await db.scalar(select(func.count()).select_from(Order)) == 1

    by_role = await async_client.get(f"/api/manager/orders/{order.id}/equipment-identities", headers=headers,
                                     params={"equipment_id": registered.id})
    assert by_role.status_code == 200, by_role.text
    assert by_role.json()["candidate"]["equipment_id"] == registered.id

    branches[0].delivery_address = "Изменённый адрес филиала"
    await db.commit()
    snapshots = await async_client.get(path, headers=headers)
    assert snapshots.json()["legacy_primary"] is None
    assert snapshots.json()["items"][0]["address"] == "Основная площадка по заказу"
    assert (await async_client.get(path, headers=headers, params={"limit": 101})).status_code == 422
    assert (await async_client.get(f"{path}/{site_a['id']}/equipment", headers=headers, params={"limit": 101})).status_code == 422


@pytest.mark.asyncio
async def test_order_site_scope_conflicts_leave_no_partial_equipment_or_customer_reassignment(async_client, db):
    user, customer, outsider, branches, foreign_branch, order = await make_workspace(db)
    headers = _headers(user)
    path = f"/api/manager/orders/{order.id}/sites"

    missing_branch = await post_command(
        async_client, headers, path, "foreign-branch-add-0001", {"customer_branch_id": foreign_branch.id},
    )
    assert missing_branch.status_code == 404, missing_branch.text

    site_a = await add_site(async_client, headers, path, "site-a-scoped-create", {"customer_branch_id": branches[0].id})
    site_b = await add_site(async_client, headers, path, "site-b-scoped-create", {"customer_branch_id": branches[1].id})
    unit_wrong_customer = CustomerEquipment(customer_id=outsider.id, model="TEST-FOREIGN")
    unit_wrong_branch = CustomerEquipment(customer_id=customer.id, customer_branch_id=branches[1].id, model="TEST-B")
    unit_unassigned = CustomerEquipment(customer_id=customer.id, model="TEST-UNASSIGNED")
    db.add_all([unit_wrong_customer, unit_wrong_branch, unit_unassigned])
    await db.commit()

    path_a = f"{path}/{site_a['id']}/equipment"
    path_b = f"{path}/{site_b['id']}/equipment"

    for key, unit in (("foreign-unit-customer", unit_wrong_customer), ("foreign-unit-branch", unit_wrong_branch)):
        response = await post_command(
            async_client, headers, path_a, key, {"expected_version": site_a["version"], "equipment_id": unit.id},
        )
        assert response.status_code == 400, response.text

    request = {"expected_version": site_a["version"], "equipment_id": unit_unassigned.id}
    preference = await post_command(async_client, headers, path_a, "first-linked-unit-0001", request)
    assert preference.status_code == 200, preference.text
    replay_changed = await post_command(
        async_client, headers, path_a, "first-linked-unit-0001", {**request, "role": "repair"},
    )
    assert replay_changed.status_code == 409
    already_assigned = await post_command(
        async_client, headers, path_b, "second-linked-unit-0001",
        {"expected_version": site_b["version"], "equipment_id": unit_unassigned.id},
    )
    assert already_assigned.status_code == 409, already_assigned.text
    stale = await post_command(
        async_client, headers, path_a, "unique-stale-unit-0001",
        {"expected_version": site_a["version"], "equipment": {"display_name": "Ошибка версии"}},
    )
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "version_conflict"
    assert await db.scalar(select(func.count()).select_from(CustomerEquipment)) == 3
    assert await db.scalar(select(func.count()).select_from(OrderSiteEquipment)) == 1

    change_customer = await async_client.patch(
        f"/api/manager/orders/{order.id}", headers=headers, json={"customer_id": outsider.id},
    )
    assert change_customer.status_code == 400, change_customer.text
    await db.refresh(order)
    assert order.customer_id == customer.id

    with pytest.raises(ValueError, match="относится к этому объекту"):
        await OrderSiteService.resolve_scope(db, TenantScope(1, 1), order.id, site_b["id"], [unit_unassigned.id])


@pytest.mark.asyncio
async def test_sites_cannot_be_read_or_linked_across_orders_tenants_and_storefronts(async_client, db):
    user, customer, _, branches, _, order = await make_workspace(db)
    headers = _headers(user)
    path = f"/api/manager/orders/{order.id}/sites"
    site = await add_site(async_client, headers, path, "sites-isolation-create", {"customer_branch_id": branches[0].id})
    tenant = Tenant(id=2, slug="sites-other-tenant", display_name="Other test tenant")
    db.add(tenant)
    await db.flush()
    other_front = Storefront(id=2, tenant_id=1, slug="sites-other-front", display_name="Other test storefront")
    other_tenant_front = Storefront(id=3, tenant_id=tenant.id, slug="main", display_name="Other test tenant")
    tenant_customer = Customer(tenant_id=tenant.id, name="Other tenant customer", phone="")
    db.add_all([other_front, other_tenant_front, tenant_customer])
    await db.flush()
    hidden_equipment = CustomerEquipment(customer_id=tenant_customer.id, model="TEST-TENANT")
    same_front_order = Order(tenant_id=1, storefront_id=1, customer_id=customer.id, status=OrderStatus.NEGOTIATION)
    other_front_order = Order(tenant_id=1, storefront_id=other_front.id, customer_id=customer.id, status=OrderStatus.NEGOTIATION)
    other_tenant_order = Order(
        tenant_id=tenant.id, storefront_id=other_tenant_front.id, customer_id=tenant_customer.id,
        status=OrderStatus.NEGOTIATION,
    )
    db.add_all([hidden_equipment, same_front_order, other_front_order, other_tenant_order])
    await db.commit()

    for hidden_order in (other_front_order, other_tenant_order):
        response = await async_client.get(f"/api/manager/orders/{hidden_order.id}/sites", headers=headers)
        assert response.status_code == 404, response.text
    foreign_site = await async_client.get(
        f"/api/manager/orders/{same_front_order.id}/sites/{site['id']}/equipment", headers=headers,
    )
    assert foreign_site.status_code == 404, foreign_site.text

    response = await post_command(
        async_client, headers, f"{path}/{site['id']}/equipment", "wrong-tenant-unit-0001",
        {"expected_version": site["version"], "equipment_id": hidden_equipment.id},
    )
    assert response.status_code == 404, response.text
    actor = CommandActor(user.id, user.username, TenantScope(1, 1), "chatgpt")
    with pytest.raises(LookupError):
        await OrderSiteService.list_sites(db, actor, other_front_order.id)

    order.status = OrderStatus.CLOSED
    await db.commit()
    assert (await async_client.get(path, headers=headers)).status_code == 200
    closed = await post_command(
        async_client, headers, path, "closed-order-site-create",
        {"title": "Поздний объект", "address": "Тестовый адрес"},
    )
    assert closed.status_code == 409, closed.text


@pytest.mark.asyncio
async def test_parallel_equipment_writes_respect_site_version_and_retry_receipt(db_engine):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        user, _, _, branches, _, order = await make_workspace(session)
        actor = CommandActor(user.id, user.username, TenantScope(1, 1), "chatgpt")
        created = await OrderSiteService.add_site(
            session, actor, order.id, OrderSiteAddPayload(customer_branch_id=branches[0].id),
            idempotency_key="parallel-order-site-create",
        )
        site = created.value

    first = OrderSiteEquipmentLinkPayload(
        expected_version=site.version, equipment={"display_name": "Первый тестовый блок"},
    )
    second = OrderSiteEquipmentLinkPayload(
        expected_version=site.version, equipment={"display_name": "Второй тестовый блок"},
    )
    start = asyncio.Barrier(2)

    async def attach(key, payload):
        async with session_factory() as session:
            await start.wait()
            return await OrderSiteService.link_equipment(
                session, actor, order.id, site.id, payload, idempotency_key=key,
            )

    outcomes = await asyncio.gather(
        attach("parallel-test-site-link-first", first),
        attach("parallel-test-site-link-second", second),
        return_exceptions=True,
    )
    winner = next(index for index, outcome in enumerate(outcomes) if not isinstance(outcome, BaseException))
    assert isinstance(outcomes[1 - winner], OrderSiteVersionConflict)
    payload, key = (
        (first, "parallel-test-site-link-first"),
        (second, "parallel-test-site-link-second"),
    )[winner]
    async with session_factory() as session:
        replay = await OrderSiteService.link_equipment(session, actor, order.id, site.id, payload, idempotency_key=key)
        assert replay.replayed and replay.value == outcomes[winner].value
        assert await session.scalar(select(func.count()).select_from(CustomerEquipment)) == 1
        assert await session.scalar(select(func.count()).select_from(OrderSiteEquipment)) == 1


@pytest.mark.asyncio
async def test_legacy_unlink_only_protects_the_role_required_by_an_explicit_site(async_client, db):
    user, customer, _, branches, _, order = await make_workspace(db)
    headers = _headers(user)
    path = f"/api/manager/orders/{order.id}"
    site = await add_site(
        async_client, headers, f"{path}/sites", "site-projection-create-01", {"customer_branch_id": branches[0].id},
    )
    equipment_path = f"{path}/sites/{site['id']}/equipment"
    attached = await post_command(
        async_client, headers, equipment_path, "site-projection-equipment-01",
        {"expected_version": site["version"], "equipment": {"display_name": "Тестовый блок"}},
    )
    assert attached.status_code == 200, attached.text
    equipment_id = attached.json()["result"]["equipment"]["equipment_id"]
    legacy_path = f"{path}/equipment-links"
    projected_id = await db.scalar(select(EquipmentOrderLink.id).where(
        EquipmentOrderLink.order_id == order.id,
        EquipmentOrderLink.equipment_id == equipment_id,
        EquipmentOrderLink.role == "diagnostic",
    ))
    assert projected_id is not None

    other_role = await async_client.post(
        legacy_path, headers=headers, json={"equipment_id": equipment_id, "role": "repair"},
    )
    assert other_role.status_code == 201, other_role.text
    blocked = await async_client.delete(f"{legacy_path}/{projected_id}", headers=headers)
    assert blocked.status_code == 409, blocked.text
    assert "привязано к объекту" in blocked.json()["detail"]
    removed = await async_client.delete(f"{legacy_path}/{other_role.json()['link_id']}", headers=headers)
    assert removed.status_code == 204, removed.text

    unscoped = CustomerEquipment(customer_id=customer.id, model="TEST-LEGACY")
    db.add(unscoped)
    await db.commit()
    legacy_only = await async_client.post(
        legacy_path, headers=headers, json={"equipment_id": unscoped.id, "role": "diagnostic"},
    )
    assert legacy_only.status_code == 201, legacy_only.text
    removed = await async_client.delete(f"{legacy_path}/{legacy_only.json()['link_id']}", headers=headers)
    assert removed.status_code == 204, removed.text

    remaining = await async_client.get(legacy_path, headers=headers)
    assert remaining.status_code == 200, remaining.text
    assert [item["link_id"] for item in remaining.json()["items"]] == [projected_id]
    current_site = await async_client.get(equipment_path, headers=headers)
    assert current_site.status_code == 200, current_site.text
    assert [item["equipment_id"] for item in current_site.json()["items"]] == [equipment_id]
