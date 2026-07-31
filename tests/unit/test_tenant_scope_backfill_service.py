from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from crud.tenant_scope_backfill import TenantScopeBackfillDAO
from models import Lead, Order, Storefront, Tenant
from scripts.backfill_lead_order_tenant_scope import build_parser, validate_args
from services.tenant_scope_backfill_service import (
    TenantScopeBackfillBlockedError,
    TenantScopeBackfillService,
)


pytestmark = pytest.mark.expand_phase_schema


async def _add_legacy_rows(db, *, leads: int, orders: int) -> tuple[list[Lead], list[Order]]:
    lead_rows = [Lead(request_text=f"Legacy lead {index}") for index in range(leads)]
    order_rows = [Order(title=f"Legacy order {index}") for index in range(orders)]
    db.add_all([*lead_rows, *order_rows])
    await db.commit()
    return lead_rows, order_rows


@pytest.mark.asyncio
async def test_dry_run_is_bounded_deterministic_and_read_only(db):
    legacy_leads, legacy_orders = await _add_legacy_rows(db, leads=2, orders=2)
    db.add_all(
        [
            Lead(request_text="Already scoped lead", tenant_id=1, storefront_id=1),
            Order(title="Already scoped order", tenant_id=1, storefront_id=1),
        ]
    )
    await db.commit()

    result = await TenantScopeBackfillService.run(
        db,
        execute=False,
        limit_per_table=1,
    )
    repeated = await TenantScopeBackfillService.run(
        db,
        execute=False,
        limit_per_table=1,
    )

    assert result["dry_run"] is True
    assert result["ready_for_backfill"] is True
    assert result["contract_ready"] is False
    assert result["before"]["lead"] == {
        "entity": "lead",
        "total": 3,
        "legacy_null": 2,
        "target_scoped": 1,
        "partial": 0,
        "unexpected_scoped": 0,
        "unknown_tenant": 0,
        "unknown_storefront": 0,
        "cross_tenant": 0,
    }
    assert result["before"]["order"]["legacy_null"] == 2
    assert result["before"]["order"]["target_scoped"] == 1
    assert result["planned"] == {
        "lead": [int(legacy_leads[0].id)],
        "order": [int(legacy_orders[0].id)],
    }
    assert len(result["plan_token"]) == 64
    assert repeated["plan_token"] == result["plan_token"]

    stored_leads = (await db.execute(select(Lead).order_by(Lead.id))).scalars().all()
    stored_orders = (await db.execute(select(Order).order_by(Order.id))).scalars().all()
    assert sum(item.tenant_id is None for item in stored_leads) == 2
    assert sum(item.tenant_id is None for item in stored_orders) == 2


@pytest.mark.asyncio
async def test_execute_backfills_exact_reviewed_batches_and_is_idempotent(db):
    await _add_legacy_rows(db, leads=2, orders=2)

    canary = await TenantScopeBackfillService.run(
        db,
        execute=False,
        limit_per_table=1,
    )
    canary_result = await TenantScopeBackfillService.run(
        db,
        execute=True,
        limit_per_table=1,
        expected_tenant_id=1,
        expected_storefront_id=1,
        plan_token=canary["plan_token"],
    )

    assert canary_result["updated"] == {"lead": 1, "order": 1}
    assert canary_result["after"]["lead"]["legacy_null"] == 1
    assert canary_result["after"]["order"]["legacy_null"] == 1
    assert canary_result["contract_ready"] is False

    remainder = await TenantScopeBackfillService.run(
        db,
        execute=False,
        limit_per_table=10,
    )
    final_result = await TenantScopeBackfillService.run(
        db,
        execute=True,
        limit_per_table=10,
        expected_tenant_id=1,
        expected_storefront_id=1,
        plan_token=remainder["plan_token"],
    )

    assert final_result["updated"] == {"lead": 1, "order": 1}
    assert final_result["after"]["lead"]["legacy_null"] == 0
    assert final_result["after"]["order"]["legacy_null"] == 0
    assert final_result["contract_ready"] is True

    no_op_plan = await TenantScopeBackfillService.run(
        db,
        execute=False,
        limit_per_table=10,
    )
    no_op_result = await TenantScopeBackfillService.run(
        db,
        execute=True,
        limit_per_table=10,
        expected_tenant_id=1,
        expected_storefront_id=1,
        plan_token=no_op_plan["plan_token"],
    )
    assert no_op_result["updated"] == {"lead": 0, "order": 0}
    assert no_op_result["contract_ready"] is True


@pytest.mark.asyncio
async def test_execute_preserves_business_updated_at_timestamps(db):
    lead_updated_at = datetime(2024, 2, 3, 4, 5, 6)
    order_updated_at = datetime(2024, 5, 6, 7, 8, 9)
    lead = Lead(
        request_text="Historical lead",
        updated_at=lead_updated_at,
    )
    order = Order(
        title="Historical order",
        updated_at=order_updated_at,
    )
    db.add_all([lead, order])
    await db.commit()

    reviewed = await TenantScopeBackfillService.run(
        db,
        execute=False,
        limit_per_table=10,
    )
    await TenantScopeBackfillService.run(
        db,
        execute=True,
        limit_per_table=10,
        expected_tenant_id=1,
        expected_storefront_id=1,
        plan_token=reviewed["plan_token"],
    )
    await db.refresh(lead)
    await db.refresh(order)

    assert lead.updated_at == lead_updated_at
    assert order.updated_at == order_updated_at


@pytest.mark.asyncio
async def test_execute_rejects_stale_plan_without_partial_writes(db):
    await _add_legacy_rows(db, leads=1, orders=1)
    reviewed = await TenantScopeBackfillService.run(
        db,
        execute=False,
        limit_per_table=10,
    )
    db.add(Lead(request_text="Arrived after review"))
    await db.commit()

    with pytest.raises(
        TenantScopeBackfillBlockedError,
        match="plan token is stale",
    ):
        await TenantScopeBackfillService.run(
            db,
            execute=True,
            limit_per_table=10,
            expected_tenant_id=1,
            expected_storefront_id=1,
            plan_token=reviewed["plan_token"],
        )

    leads = (await db.execute(select(Lead))).scalars().all()
    orders = (await db.execute(select(Order))).scalars().all()
    assert all(item.tenant_id is None and item.storefront_id is None for item in leads)
    assert all(item.tenant_id is None and item.storefront_id is None for item in orders)


@pytest.mark.asyncio
async def test_review_token_allows_concurrent_correctly_scoped_writes(db):
    await _add_legacy_rows(db, leads=1, orders=1)
    reviewed = await TenantScopeBackfillService.run(
        db,
        execute=False,
        limit_per_table=10,
    )
    db.add(Order(title="New scoped write", tenant_id=1, storefront_id=1))
    await db.commit()

    result = await TenantScopeBackfillService.run(
        db,
        execute=True,
        limit_per_table=10,
        expected_tenant_id=1,
        expected_storefront_id=1,
        plan_token=reviewed["plan_token"],
    )

    assert result["updated"] == {"lead": 1, "order": 1}
    assert result["after"]["order"]["target_scoped"] == 2
    assert result["contract_ready"] is True


@pytest.mark.asyncio
async def test_preflight_blocks_partial_foreign_and_cross_tenant_rows(db):
    second_tenant = Tenant(
        id=2,
        slug="other",
        display_name="Other tenant",
        status="active",
        is_system=False,
    )
    db.add(second_tenant)
    await db.flush()
    second_storefront = Storefront(
        id=2,
        tenant_id=int(second_tenant.id),
        slug="main",
        display_name="Other storefront",
        status="active",
        is_default=True,
    )
    db.add(second_storefront)
    await db.flush()
    db.add_all(
        [
            Lead(
                request_text="Partial provenance",
                tenant_id=1,
                storefront_id=None,
            ),
            Order(
                title="Foreign valid scope",
                tenant_id=int(second_tenant.id),
                storefront_id=int(second_storefront.id),
            ),
            Order(
                title="Cross-tenant pair",
                tenant_id=1,
                storefront_id=int(second_storefront.id),
            ),
        ]
    )
    await db.commit()

    report = await TenantScopeBackfillService.run(
        db,
        execute=False,
        limit_per_table=10,
    )

    assert report["ready_for_backfill"] is False
    assert report["before"]["lead"]["partial"] == 1
    assert report["before"]["order"]["unexpected_scoped"] == 2
    assert report["before"]["order"]["cross_tenant"] == 1
    assert "lead: partial=1" in report["blockers"]
    assert "order: unexpected_scoped=2" in report["blockers"]
    assert "order: cross_tenant=1" in report["blockers"]

    with pytest.raises(
        TenantScopeBackfillBlockedError,
        match="blocking provenance anomalies",
    ):
        await TenantScopeBackfillService.run(
            db,
            execute=True,
            limit_per_table=10,
            expected_tenant_id=1,
            expected_storefront_id=1,
            plan_token=report["plan_token"],
        )


@pytest.mark.asyncio
async def test_execute_rejects_scope_ids_that_differ_from_dry_run(db):
    await _add_legacy_rows(db, leads=1, orders=1)
    reviewed = await TenantScopeBackfillService.run(
        db,
        execute=False,
        limit_per_table=10,
    )

    with pytest.raises(
        TenantScopeBackfillBlockedError,
        match="do not match the reviewed scope",
    ):
        await TenantScopeBackfillService.run(
            db,
            execute=True,
            limit_per_table=10,
            expected_tenant_id=99,
            expected_storefront_id=1,
            plan_token=reviewed["plan_token"],
        )


@pytest.mark.asyncio
async def test_execute_refuses_a_concurrent_backfill_transaction(db_engine):
    session_factory = sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as lock_owner, session_factory() as contender:
        assert await TenantScopeBackfillDAO.try_acquire_transaction_lock(lock_owner)

        with pytest.raises(
            TenantScopeBackfillBlockedError,
            match="already running",
        ):
            await TenantScopeBackfillService.run(
                contender,
                execute=True,
                limit_per_table=10,
                expected_tenant_id=1,
                expected_storefront_id=1,
                plan_token="0" * 64,
            )

        await contender.rollback()
        await lock_owner.rollback()


@pytest.mark.asyncio
async def test_limit_is_strictly_bounded():
    with pytest.raises(ValueError, match="between 1 and 1000"):
        await TenantScopeBackfillService.run(
            object(),
            execute=False,
            limit_per_table=0,
        )
    with pytest.raises(ValueError, match="between 1 and 1000"):
        await TenantScopeBackfillService.run(
            object(),
            execute=False,
            limit_per_table=1001,
        )


def test_cli_requires_dry_run_confirmation_for_execute():
    parser = build_parser()
    args = parser.parse_args(["--execute"])

    with pytest.raises(SystemExit):
        validate_args(args, parser)


def test_cli_does_not_allow_operator_selected_scope():
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["--tenant-slug", "other"])
