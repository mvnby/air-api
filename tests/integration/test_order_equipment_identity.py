"""Physical equipment survives chat retries, reopening and document revisions."""

from datetime import datetime

import pytest
from sqlalchemy import func
from sqlmodel import select

from core.command_actor import CommandActor
from models import Customer, CustomerEquipment, DocumentLegalEntity, Order, OrderDocument, OrderStatus, StaffUser
from models.tenancy import TenantScope
from schemas_order_equipment_identity import OrderEquipmentSaveInput
from services.order_equipment_identity_service import OrderEquipmentIdentityService as Equipment
from services.public_write_idempotency_service import PublicWriteIdempotencyConflict


async def seed(db):
    user = StaffUser(username="equipment-manager", display_name="Equipment manager", primary_role="admin", roles=["admin"])
    customer = Customer(tenant_id=1, name="Test physical equipment", phone="")
    db.add_all([user, customer])
    await db.flush()
    order = Order(tenant_id=1, storefront_id=1, customer_id=customer.id,
                  status=OrderStatus.NEGOTIATION, workflow_type="installation")
    db.add(order)
    await db.commit()
    return CommandActor(user.id, user.username, TenantScope(1, 1), "chatgpt"), order


async def save(db, actor, order, key, **fields):
    state = await Equipment.read(db, actor, order.id)
    data = OrderEquipmentSaveInput(order_id=order.id, expected_version=state.version,
                                  idempotency_key=key, **fields)
    return await Equipment.save(db, actor, data)


async def legacy_document(db, order_id, values):
    issuer = DocumentLegalEntity(tenant_id=1, slug="equipment-test-issuer", display_name="Test issuer")
    db.add(issuer)
    await db.flush()
    document = OrderDocument(tenant_id=1, legal_entity_id=issuer.id, internal_reference="test-issued-001",
        order_id=order_id, number="TEST-001", doc_type="b2c_customer_equipment_installation_act",
        status="issued", date=datetime(2026, 11, 10), render_snapshot={"values": values})
    db.add(document)
    await db.commit()
    return document


@pytest.mark.asyncio
async def test_save_and_replay_physical_identity_without_merging_same_model(db):
    actor, order = await seed(db)
    state = await Equipment.read(db, actor, order.id)
    data = OrderEquipmentSaveInput(order_id=order.id, expected_version=state.version,
        idempotency_key="equipment-test-create-0001", brand="TEST", model="TEST-09", serial="TEST-SN-001")
    created = await Equipment.save(db, actor, data)
    replay = await Equipment.save(db, actor, data)
    assert replay.replayed and replay.value.equipment_id == created.value.equipment_id
    second = await save(db, actor, order, "equipment-test-create-0002", brand="TEST", model="TEST-09", serial="TEST-SN-002")
    unknown = await save(db, actor, order, "equipment-test-create-0003", model="TEST-09", serial="")
    assert len({created.value.equipment_id, second.value.equipment_id, unknown.value.equipment_id}) == 3
    reopened = await Equipment.read(db, actor, order.id)
    assert {item.serial for item in reopened.items} == {"TEST-SN-001", "TEST-SN-002", None}
    assert await db.scalar(select(func.count()).select_from(CustomerEquipment)) == 3


@pytest.mark.asyncio
async def test_legacy_snapshot_can_be_saved_again_without_new_identity(db):
    actor, order = await seed(db)
    document = await legacy_document(db, order.id,
        {"equipment.brand": "TEST", "equipment.model": "TEST-09", "equipment.serial": "TEST-SN-001"})
    original = document.render_snapshot.copy()
    first = await save(db, actor, order, "equipment-test-legacy-0001", source_document_id=document.id)
    second = await save(db, actor, order, "equipment-test-legacy-0002", source_document_id=document.id)
    assert first.value.equipment_id == second.value.equipment_id
    assert first.value.equipment.model == "TEST-09" and first.value.equipment.serial == "TEST-SN-001"
    assert await db.scalar(select(func.count()).select_from(CustomerEquipment)) == 1
    await db.refresh(document)
    assert document.render_snapshot == original


@pytest.mark.asyncio
async def test_stale_order_version_and_changed_key_payload_do_not_create_units(db):
    actor, order = await seed(db)
    state = await Equipment.read(db, actor, order.id)
    data = OrderEquipmentSaveInput(order_id=order.id, expected_version=state.version,
        idempotency_key="equipment-test-key-00001", model="TEST-09", serial="SN")
    await Equipment.save(db, actor, data)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as stale:
        await Equipment.save(db, actor, data.model_copy(update={"idempotency_key": "equipment-test-stale-001"}))
    assert stale.value.status_code == 409
    with pytest.raises(PublicWriteIdempotencyConflict):
        await Equipment.save(db, actor, data.model_copy(update={"serial": "different"}))
    assert await db.scalar(select(func.count()).select_from(CustomerEquipment)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("foreign", ["tenant", "storefront", "customer", "branch", "document"])
async def test_equipment_commands_reject_foreign_bindings(db, foreign):
    from models import CustomerBranch
    from models.tenancy import Storefront, Tenant

    actor, order = await seed(db)
    db.add(Tenant(id=2, slug="equipment-foreign", display_name="Foreign"))
    await db.flush()
    db.add_all([Storefront(id=2, tenant_id=2, slug="main", display_name="Foreign"),
                Storefront(id=3, tenant_id=1, slug="other", display_name="Other")])
    customer = Customer(tenant_id=2 if foreign == "tenant" else 1, name="Other customer", phone="")
    db.add(customer)
    await db.flush()
    branch_a, branch_b = CustomerBranch(customer_id=order.customer_id, name="A", delivery_address="Test A"), CustomerBranch(customer_id=order.customer_id, name="B", delivery_address="Test B")
    db.add_all([branch_a, branch_b])
    await db.flush()
    if foreign == "branch":
        order.customer_branch_id = branch_a.id
    equipment = CustomerEquipment(customer_id=customer.id if foreign in {"customer", "tenant"} else order.customer_id,
        customer_branch_id=branch_b.id if foreign == "branch" else None, model="TEST")
    db.add(equipment)
    other_order = Order(tenant_id=2 if foreign == "tenant" else 1,
        storefront_id=2 if foreign == "tenant" else 3, customer_id=customer.id, status=OrderStatus.NEGOTIATION)
    db.add(other_order)
    await db.flush()
    source = await legacy_document(db, other_order.id, {"equipment.model": "FOREIGN"})
    if foreign in {"tenant", "storefront"}:
        with pytest.raises(LookupError):
            await Equipment.read(db, actor, other_order.id)
    elif foreign == "document":
        with pytest.raises(LookupError):
            await save(db, actor, order, "equipment-test-foreign01", source_document_id=source.id)
    else:
        with pytest.raises(ValueError):
            await save(db, actor, order, "equipment-test-foreign01", equipment_id=equipment.id)
    assert await db.scalar(select(func.count()).select_from(CustomerEquipment)) == 1


@pytest.mark.asyncio
async def test_existing_sale_is_reused_and_omitted_fields_survive_versioned_patch(db):
    actor, order = await seed(db)
    sold = CustomerEquipment(customer_id=order.customer_id, equipment_source="sold_by_us", brand="TEST", model="TEST-09", serial="SALE-SN")
    db.add(sold)
    await db.commit()
    linked = await save(db, actor, order, "equipment-test-link-sale01", equipment_id=sold.id)
    assert linked.value.equipment_id == sold.id
    assert linked.value.equipment.equipment_source == "sold_by_us"
    state = await Equipment.read(db, actor, order.id)
    stale_equipment_version = state.items[0].version
    sold.model = "Concurrent edit"
    await db.commit()
    current = await Equipment.read(db, actor, order.id)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        await Equipment.save(db, actor, OrderEquipmentSaveInput(order_id=order.id,
            expected_version=current.version, equipment_id=sold.id, expected_equipment_version=stale_equipment_version,
            serial="corrected", idempotency_key="equipment-test-stale-0001"))
    assert error.value.status_code == 409
    await db.refresh(sold)
    assert sold.serial == "SALE-SN" and sold.model == "Concurrent edit"
    updated = await save(db, actor, order, "equipment-test-patch-0001", equipment_id=sold.id,
        expected_equipment_version=current.items[0].version, serial="corrected")
    assert updated.value.equipment.brand == "TEST" and updated.value.equipment.model == "Concurrent edit"
    assert await db.scalar(select(func.count()).select_from(CustomerEquipment)) == 1


@pytest.mark.asyncio
async def test_manager_equipment_command_uses_same_saved_identity_and_versions(async_client, db):
    from models.tenancy import TenantMembership
    from tests.integration.test_manager_access_permissions import _headers

    actor, order = await seed(db)
    db.add(TenantMembership(tenant_id=1, staff_user_id=actor.staff_user_id, role="admin"))
    await db.commit()
    user = await db.get(StaffUser, actor.staff_user_id)
    headers = _headers(user)
    path = f"/api/manager/orders/{order.id}/equipment-identities"
    read = await async_client.get(path, headers=headers)
    assert read.status_code == 200, read.text
    payload = {"expected_version": read.json()["version"], "idempotency_key": "equipment-manager-save-0001",
               "brand": "TEST", "model": "TEST-09", "serial": ""}
    created = await async_client.post(path, headers=headers, json=payload)
    assert created.status_code == 200, created.text
    replay = await async_client.post(path, headers=headers, json=payload)
    assert replay.status_code == 200 and replay.json()["replayed"], replay.text
    equipment_id = created.json()["result"]["equipment_id"]
    current = await async_client.get(path, headers=headers, params={"equipment_id": equipment_id})
    assert current.status_code == 200
    assert current.json()["candidate"]["equipment_id"] == equipment_id
    assert current.json()["candidate"]["model"] == "TEST-09" and current.json()["candidate"]["serial"] is None
    stale = await async_client.post(path, headers=headers,
        json={**payload, "idempotency_key": "equipment-manager-stale-0001"})
    assert stale.status_code == 409
    assert (await async_client.get(path, headers=headers, params={"limit": 101})).status_code == 422


@pytest.mark.asyncio
async def test_sale_workflow_unit_is_reused_when_recording_its_serial(db):
    from models import OrderProductLink, Product
    from services.equipment_workflow_service import EquipmentWorkflowService

    actor, order = await seed(db)
    product = Product(title="TEST-09", slug="test-sale-equipment", price=1000)
    db.add(product)
    await db.flush()
    db.add(OrderProductLink(order_id=order.id, product_id=product.id, quantity=1, price=1000))
    await db.commit()
    await EquipmentWorkflowService.create_equipment_from_order(db, order_id=order.id,
        tenant_scope=actor.tenant_scope, payload={"include_component_placeholders": True})
    state = await Equipment.read(db, actor, order.id)
    assert state.total == 1
    sold = state.items[0]
    assert sold.catalog_product_id == product.id and sold.equipment_source == "sold_by_us"
    recorded = await save(db, actor, order, "equipment-sale-serial-0001", equipment_id=sold.equipment_id,
        expected_equipment_version=sold.version, serial="TEST-SALE-SN-001", role="sale")
    assert recorded.value.equipment_id == sold.equipment_id
    assert recorded.value.equipment.model == "TEST-09" and recorded.value.equipment.serial == "TEST-SALE-SN-001"
    assert await db.scalar(select(func.count()).select_from(CustomerEquipment)) == 1


@pytest.mark.asyncio
async def test_cached_identity_and_receipt_cannot_bypass_changed_customer(db):
    from sqlalchemy import update

    actor, order = await seed(db)
    state = await Equipment.read(db, actor, order.id)
    data = OrderEquipmentSaveInput(order_id=order.id, expected_version=state.version,
        idempotency_key="equipment-cached-access-001", model="TEST-09")
    saved = await Equipment.save(db, actor, data)
    cached = await db.get(CustomerEquipment, saved.value.equipment_id)
    other = Customer(tenant_id=1, name="Another customer's unit", phone="")
    db.add(other)
    await db.flush()
    await db.execute(update(CustomerEquipment).where(CustomerEquipment.id == cached.id)
        .values(customer_id=other.id).execution_options(synchronize_session=False))
    await db.commit()
    assert cached.customer_id == order.customer_id  # Reused session still holds the old identity.
    with pytest.raises(ValueError, match="customer"):
        await Equipment.read(db, actor, order.id, equipment_id=cached.id)
    with pytest.raises(ValueError, match="customer"):
        await Equipment.save(db, actor, data)
