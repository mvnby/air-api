import pytest

from models import Customer, CustomerType, Order, OrderStatus
from services.customer_service import CustomerService


@pytest.mark.asyncio
async def test_list_for_manager_defaults_to_only_with_orders(db, tenant_scope):
    customer_with_order = Customer(tenant_id=1, name="With Order", phone="+375291000001", type=CustomerType.individual)
    customer_without_order = Customer(tenant_id=1, name="No Order", phone="+375291000002", type=CustomerType.individual)
    db.add(customer_with_order)
    db.add(customer_without_order)
    await db.commit()
    await db.refresh(customer_with_order)
    await db.refresh(customer_without_order)

    db.add(Order(tenant_id=1, storefront_id=1, customer_id=customer_with_order.id, status=OrderStatus.NEW_LEAD))
    await db.commit()

    result_default = await CustomerService.list_for_manager(
        db,
        page=1,
        limit=20,
        tenant_scope=tenant_scope,
    )
    ids_default = {item["id"] for item in result_default["items"]}
    assert customer_with_order.id in ids_default
    assert customer_without_order.id not in ids_default

    result_all = await CustomerService.list_for_manager(
        db,
        page=1,
        limit=20,
        only_with_orders=False,
        tenant_scope=tenant_scope,
    )
    ids_all = {item["id"] for item in result_all["items"]}
    assert customer_with_order.id in ids_all
    assert customer_without_order.id in ids_all


def test_customer_model_does_not_assume_signing_requisites():
    customer = Customer(tenant_id=1, name="Unknown", phone="")
    assert customer.signer_position == customer.acting_basis == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "party,mode",
    [
        (CustomerType.company, "statutory_body"),
        (CustomerType.individual_entrepreneur, "self"),
        (CustomerType.individual, "self"),
    ],
)
async def test_customer_signing_service_preserves_tenant_scope(
    db, tenant_scope, party, mode
):
    from models import Tenant
    from models.tenancy import TenantScope
    from services.customer_creation_service import CustomerCreationService

    other_tenant = Tenant(slug="signing-other", display_name="Other")
    db.add(other_tenant)
    await db.flush()
    other_scope = TenantScope(
        tenant_id=other_tenant.id, storefront_id=None, is_system=False
    )
    created = await CustomerCreationService.create_for_manager(
        db, tenant_scope=other_scope, payload={"name": "Signing service", "type": party}
    )
    assert created["signer_position"] == created["acting_basis"] == ""
    assert created["signing_mode"] == mode
    denied = await CustomerService.update_for_manager(
        db,
        customer_id=created["id"],
        tenant_scope=tenant_scope,
        payload={"signer_position": "Unexpected", "acting_basis": "Unexpected"},
    )
    assert denied is None
    stored = await db.get(Customer, created["id"])
    assert stored.tenant_id == other_tenant.id
    assert stored.signer_position == stored.acting_basis == ""
    supplied = {"signer_position": " директора ", "acting_basis": " Устава "}
    updated = await CustomerService.update_for_manager(
        db, customer_id=created["id"], tenant_scope=other_scope, payload=supplied
    )
    assert updated["signer_position"] == "директора"
    assert updated["acting_basis"] == "Устава"
    omitted = await CustomerService.update_for_manager(
        db, customer_id=created["id"], tenant_scope=other_scope, payload={}
    )
    assert omitted["signer_position"] == "директора"
    assert omitted["acting_basis"] == "Устава"
