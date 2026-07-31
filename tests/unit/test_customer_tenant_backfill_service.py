from datetime import datetime

import pytest
from sqlmodel import select

from models import Customer, CustomerRequisitesRecognition, Tenant
from services.customer_tenant_backfill_service import (
    CustomerTenantBackfillBlockedError,
    CustomerTenantBackfillService,
)


pytestmark = pytest.mark.expand_phase_schema


@pytest.mark.asyncio
async def test_customer_backfill_is_bounded_reviewed_and_preserves_recency(db):
    original_updated_at = datetime(2025, 1, 2, 3, 4, 5)
    customers = [
        Customer(name="Legacy 1", phone="+375290000001"),
        Customer(name="Legacy 2", phone="+375290000002"),
    ]
    recognitions = [
        CustomerRequisitesRecognition(
            source="manager",
            raw_text="legacy recognition 1",
            updated_at=original_updated_at,
        ),
        CustomerRequisitesRecognition(
            source="manager",
            raw_text="legacy recognition 2",
        ),
    ]
    db.add_all([*customers, *recognitions])
    await db.commit()

    reviewed = await CustomerTenantBackfillService.run(
        db,
        execute=False,
        limit_per_table=1,
    )
    assert reviewed["ready_for_backfill"] is True
    assert reviewed["contract_ready"] is False
    assert reviewed["planned"]["customer"] == [customers[0].id]
    assert reviewed["planned"]["recognition"] == [recognitions[0].id]

    executed = await CustomerTenantBackfillService.run(
        db,
        execute=True,
        limit_per_table=1,
        expected_tenant_id=reviewed["tenant_id"],
        expected_storefront_id=reviewed["storefront_id"],
        plan_token=reviewed["plan_token"],
    )
    await db.commit()
    assert executed["updated"] == {"customer": 1, "recognition": 1}
    await db.refresh(recognitions[0])
    assert recognitions[0].tenant_id == 1
    assert recognitions[0].updated_at == original_updated_at

    remainder = await CustomerTenantBackfillService.run(
        db,
        execute=False,
        limit_per_table=100,
    )
    completed = await CustomerTenantBackfillService.run(
        db,
        execute=True,
        limit_per_table=100,
        expected_tenant_id=remainder["tenant_id"],
        expected_storefront_id=remainder["storefront_id"],
        plan_token=remainder["plan_token"],
    )
    await db.commit()
    assert completed["contract_ready"] is True
    final = await CustomerTenantBackfillService.run(
        db,
        execute=False,
        limit_per_table=100,
    )
    assert final["contract_ready"] is True
    assert final["before"]["customer"]["legacy_null"] == 0
    assert final["before"]["recognition"]["legacy_null"] == 0


@pytest.mark.asyncio
async def test_customer_backfill_rejects_stale_plan(db):
    customer = Customer(name="Legacy", phone="+375290000003")
    db.add(customer)
    await db.commit()
    reviewed = await CustomerTenantBackfillService.run(
        db,
        execute=False,
        limit_per_table=10,
    )

    db.add(Customer(name="New Legacy", phone="+375290000004"))
    await db.commit()
    with pytest.raises(
        CustomerTenantBackfillBlockedError,
        match="plan token is stale",
    ):
        await CustomerTenantBackfillService.run(
            db,
            execute=True,
            limit_per_table=10,
            expected_tenant_id=reviewed["tenant_id"],
            expected_storefront_id=reviewed["storefront_id"],
            plan_token=reviewed["plan_token"],
        )


@pytest.mark.asyncio
async def test_customer_backfill_blocks_unexpected_tenant_ownership(db):
    other_tenant = Tenant(
        id=2,
        slug="other",
        display_name="Other",
        kind="independent_seller",
        status="active",
        is_system=False,
    )
    db.add(other_tenant)
    await db.flush()
    db.add(
        Customer(
            tenant_id=2,
            name="Other tenant",
            phone="+375290000005",
        )
    )
    await db.commit()

    reviewed = await CustomerTenantBackfillService.run(
        db,
        execute=False,
        limit_per_table=10,
    )
    assert reviewed["ready_for_backfill"] is False
    assert "customer: unexpected_scoped=1" in reviewed["blockers"]

    customers = (await db.execute(select(Customer))).scalars().all()
    assert customers[0].tenant_id == 2
