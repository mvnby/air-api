"""Waiting, child-command conflicts and money/stage invariants on isolated PostgreSQL."""

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from api_contracts.order_waiting import ManagerOrderWaitingCommand as Command
from core.config import settings
from models import (
    Order,
    OrderProposal,
    OrderServiceLink,
    OrderWorkStage,
    TenantAuditEvent,
)
from models.tenancy import TenantScope
from schemas import (
    OrderWorkStageCreatePayload,
    OrderWorkStageUpdatePayload,
    PaymentCreatePayload,
    ManagerOrderUpdatePayload,
)
from services.order_waiting_service import OrderWaitingService, OrderWaitingError
from services.order_work_stage_command_service import OrderWorkStageCommandService
from services.order_payment_command_service import OrderPaymentCommandService
from services.order_update.command import OrderUpdateCommandService
from services.order_projection_service import OrderProjectionService
from services.order_board_projection import OrderBoardProjection
from services.scheduler_service import SchedulerService
from services.tenant_entity_access_service import TenantEntityAccessService

SCOPE = TenantScope(tenant_id=1, storefront_id=1)
ACTOR = SimpleNamespace(staff_user_id=None, username="waiting-test")


async def seed(db, **kwargs):
    kwargs.setdefault("total_amount", 1000)
    kwargs.setdefault("balance_due", 1000)
    kwargs.setdefault("margin", 800)
    order = Order(
        tenant_id=1,
        storefront_id=1,
        status="execution",
        title="One installation",
        **kwargs,
    )
    db.add(order)
    await db.flush()
    proposal = OrderProposal(order_id=order.id, is_selected=True)
    db.add(proposal)
    await db.flush()
    db.add(
        OrderServiceLink(
            order_id=order.id,
            proposal_id=proposal.id,
            title="Installation",
            price=1000,
            cost=200,
            quantity=1,
        )
    )
    await db.commit()
    return int(order.id)


async def detail(db, order_id):
    return await OrderProjectionService.get_order_detail_for_manager(
        db, order_id, tenant_scope=SCOPE, repair_legacy_state=False
    )


async def command(db, order_id, **kwargs):
    return await OrderWaitingService.execute(
        db, order_id, Command(**kwargs), auth=ACTOR, tenant_scope=SCOPE
    )


@pytest.mark.asyncio
async def test_wait_resume_preserves_order_and_history_and_gets_do_not_bump(db):
    order_id = await seed(
        db, on_hold_reason="Legacy free text", total_amount=9999, balance_due=9999
    )
    planned_date = datetime.now() + timedelta(days=10)
    visit = OrderWorkStage(
        order_id=order_id,
        name="Agreed visit",
        status="planned",
        start_time=planned_date,
    )
    db.add(visit)
    await db.commit()
    visit_id = visit.id
    initial = await detail(db, order_id)
    assert (
        initial["on_hold_started_at"] is None
        and initial["on_hold_reason"] == "Legacy free text"
    )
    before_revision = initial["workflow_revision"]
    await OrderBoardProjection.page(db, tenant_scope=SCOPE, segment="all")
    assert (await detail(db, order_id))["workflow_revision"] == before_revision
    waited = await command(
        db,
        order_id,
        action="wait",
        expected_revision=before_revision,
        reason_code="next_stage",
        note="Second visit when walls are ready",
        next_followup_date=None,
    )
    assert waited["is_on_hold"] and waited["on_hold_started_at"] is not None
    assert waited["next_followup_date"] is None and waited["status"] == "execution"
    assert waited["total_amount"] == 1000
    assert (
        await db.execute(select(Order.total_amount).where(Order.id == order_id))
    ).scalar_one() == 9999
    resumed = await command(
        db, order_id, action="resume", expected_revision=waited["workflow_revision"]
    )
    assert not resumed["is_on_hold"] and resumed["on_hold_started_at"] is None
    assert resumed["on_hold_reason"] == waited["on_hold_reason"]
    assert (
        resumed["total_amount"] == waited["total_amount"]
        and resumed["balance_due"] == waited["balance_due"]
    )
    visit = (
        await db.execute(select(OrderWorkStage).where(OrderWorkStage.id == visit_id))
    ).scalar_one()
    assert visit.status == "planned" and visit.start_time == planned_date
    events = (
        await db.scalars(
            select(TenantAuditEvent).where(
                TenantAuditEvent.entity_id == order_id,
                TenantAuditEvent.action == "order.waiting_changed",
            )
        )
    ).all()
    assert len(events) == 2 and events[0].change_set["is_on_hold"] == {
        "before": False,
        "after": True,
    }
    assert events[1].change_set["on_hold_started_at"]["after"] is None
    assert resumed["workflow_revision"] > waited["workflow_revision"] > before_revision


@pytest.mark.asyncio
async def test_legacy_held_start_and_contact_stay_unknown_and_future_contact_survives_scheduler(
    db,
):
    old = datetime.now() - timedelta(days=190)
    order = Order(
        tenant_id=1,
        storefront_id=1,
        status="negotiation",
        is_on_hold=True,
        on_hold_reason="Старое пояснение",
        updated_at=old,
        next_followup_date=None,
    )
    active_future = Order(
        tenant_id=1,
        storefront_id=1,
        status="negotiation",
        updated_at=old,
        next_followup_date=datetime.now() + timedelta(days=40),
    )
    active_due = Order(
        tenant_id=1,
        storefront_id=1,
        status="negotiation",
        updated_at=old,
        next_followup_date=datetime.now() - timedelta(days=20),
    )
    db.add_all([order, active_future, active_due])
    await db.commit()
    order_id, future_id, due_id = order.id, active_future.id, active_due.id
    contact, due_contact = (
        active_future.next_followup_date,
        active_due.next_followup_date,
    )
    for _ in range(3):
        await SchedulerService().check_stalled_deals(db)
    held = await detail(db, order_id)
    assert (
        held["is_on_hold"]
        and held["next_followup_date"] is None
        and held["on_hold_started_at"] is None
    )
    assert (
        held["on_hold_reason"] == "Старое пояснение" and held["workflow_revision"] == 0
    )
    assert (await detail(db, future_id))["next_followup_date"] == contact
    assert (await detail(db, future_id))["negotiation_status"] != "follow_up"
    assert (await detail(db, due_id))["next_followup_date"] == due_contact
    edited = await command(
        db,
        order_id,
        action="wait",
        expected_revision=0,
        reason_code="other",
        note="Legacy clarification",
    )
    assert edited["on_hold_started_at"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("amount", [0, 250, 1000])
async def test_payment_does_not_resume_or_close_waiting_order(db, amount):
    order_id = await seed(
        db,
        is_on_hold=True,
        on_hold_reason="Second stage",
        auto_close_on_payment=True,
        auto_execution_on_payment=True,
        execution_status="awaiting_payment",
    )
    original = await detail(db, order_id)
    if amount:
        await OrderPaymentCommandService.add_payment(
            db,
            order_id,
            PaymentCreatePayload(amount=amount, currency="BYN", type="prepayment"),
            tenant_scope=SCOPE,
        )
    after = await detail(db, order_id)
    assert (
        after["is_on_hold"]
        and after["status"] == "execution"
        and after["closing_result"] is None
    )
    assert (
        after["on_hold_reason"] == "Second stage"
        and after["on_hold_started_at"] is None
    )
    assert after["total_payments"] == amount and after["balance_due"] == 1000 - amount
    if amount:
        assert after["workflow_revision"] > original["workflow_revision"]
        with pytest.raises(OrderWaitingError, match="изменились"):
            await command(
                db,
                order_id,
                action="resume",
                expected_revision=original["workflow_revision"],
            )
    else:
        assert after["workflow_revision"] == original["workflow_revision"]


@pytest.mark.asyncio
async def test_prepaid_planned_first_visit_can_enter_execution_but_not_auto_close(db):
    order_id = await seed(
        db,
        auto_execution_on_payment=True,
        auto_close_on_payment=True,
        execution_status="awaiting_payment",
    )
    order = await TenantEntityAccessService.get_order(
        db, order_id, tenant_scope=SCOPE, for_update=True
    )
    order.status = "negotiation"
    db.add(order)
    await db.commit()
    await OrderWorkStageCommandService.add_order_stage(
        db,
        order_id,
        OrderWorkStageCreatePayload(name="First visit", status="planned"),
        tenant_scope=SCOPE,
    )
    await OrderPaymentCommandService.add_payment(
        db,
        order_id,
        PaymentCreatePayload(amount=1000, currency="BYN", type="prepayment"),
        tenant_scope=SCOPE,
    )
    after = await detail(db, order_id)
    assert (
        after["status"] == "execution"
        and not after["is_on_hold"]
        and after["closing_result"] is None
    )


@pytest.mark.asyncio
async def test_one_order_first_stage_wait_resume_second_stage_and_no_debt_inferred_pause(
    db,
):
    order_id = await seed(db)
    added = await OrderWorkStageCommandService.add_order_stage(
        db,
        order_id,
        OrderWorkStageCreatePayload(name="First", status="planned"),
        tenant_scope=SCOPE,
    )
    stage_id = added["work_stages"][0]["id"]
    completed = await OrderWorkStageCommandService.update_order_stage(
        db,
        order_id,
        stage_id,
        OrderWorkStageUpdatePayload(status="completed"),
        tenant_scope=SCOPE,
    )
    assert not completed["is_on_hold"] and completed["balance_due"] > 0
    waited = await command(
        db,
        order_id,
        action="wait",
        expected_revision=completed["workflow_revision"],
        reason_code="next_stage",
        next_followup_date=None,
    )
    second = await OrderWorkStageCommandService.add_order_stage(
        db,
        order_id,
        OrderWorkStageCreatePayload(name="Second", status="planned"),
        tenant_scope=SCOPE,
    )
    assert second["id"] == order_id and second["is_on_hold"]
    assert second["workflow_revision"] > waited["workflow_revision"]
    with pytest.raises(OrderWaitingError):
        await command(
            db, order_id, action="resume", expected_revision=waited["workflow_revision"]
        )
    resumed = await command(
        db, order_id, action="resume", expected_revision=second["workflow_revision"]
    )
    assert not resumed["is_on_hold"] and len(resumed["work_stages"]) == 2
    second_id = next(
        stage["id"] for stage in resumed["work_stages"] if stage["id"] != stage_id
    )
    canceled = await OrderWorkStageCommandService.update_order_stage(
        db,
        order_id,
        second_id,
        OrderWorkStageUpdatePayload(status="canceled"),
        tenant_scope=SCOPE,
    )
    assert not canceled["is_on_hold"] and canceled["closing_result"] is None


@pytest.mark.asyncio
async def test_wait_conflicts_with_payment_committed_while_parent_lock_is_held(
    db_engine,
):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as setup:
        order_id = await seed(setup)
    async with factory() as writer, factory() as waiter:
        before = await detail(waiter, order_id)
        await waiter.rollback()
        await TenantEntityAccessService.get_order(
            writer, order_id, tenant_scope=SCOPE, for_update=True
        )
        started = asyncio.create_task(
            command(
                waiter,
                order_id,
                action="wait",
                expected_revision=before["workflow_revision"],
                reason_code="next_stage",
            )
        )
        try:
            await asyncio.sleep(0.1)
            assert not started.done()
            await OrderPaymentCommandService.add_payment(
                writer,
                order_id,
                PaymentCreatePayload(amount=100, currency="BYN", type="prepayment"),
                tenant_scope=SCOPE,
            )
            with pytest.raises(OrderWaitingError):
                await asyncio.wait_for(started, 5)
        finally:
            if not started.done():
                started.cancel()
                await asyncio.gather(started, return_exceptions=True)
    async with factory() as verify:
        current = await detail(verify, order_id)
        assert current["total_payments"] == 100 and not current["is_on_hold"]


@pytest.mark.asyncio
async def test_cascading_order_update_never_loses_revision(db):
    order_id = await seed(db)
    initial = await detail(db, order_id)
    updated = await OrderUpdateCommandService.update_order_for_manager(
        db,
        order_id,
        ManagerOrderUpdatePayload(title="Revised", services=[]),
        tenant_scope=SCOPE,
    )
    assert updated["workflow_revision"] > initial["workflow_revision"]
    with pytest.raises(OrderWaitingError):
        await command(
            db,
            order_id,
            action="wait",
            expected_revision=initial["workflow_revision"],
            reason_code="next_stage",
        )


@pytest.mark.asyncio
async def test_waiting_http_contract_validation_scope_and_conflict(async_client, db):
    order_id = await seed(db)
    login = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    path = f"/api/manager/orders/{order_id}/waiting"
    invalid = await async_client.post(
        path,
        headers=headers,
        json={"action": "wait", "expected_revision": 0, "reason_code": "other"},
    )
    assert invalid.status_code == 400
    valid = await async_client.post(
        path,
        headers=headers,
        json={
            "action": "wait",
            "expected_revision": 0,
            "reason_code": "site_readiness",
            "next_followup_date": None,
        },
    )
    assert valid.status_code == 200, valid.text
    stale = await async_client.post(
        path, headers=headers, json={"action": "resume", "expected_revision": 0}
    )
    assert stale.status_code == 409
    missing = await async_client.post(
        "/api/manager/orders/999999/waiting",
        headers=headers,
        json={"action": "resume", "expected_revision": 0},
    )
    assert missing.status_code == 404
    bypass = await async_client.patch(
        f"/api/manager/orders/{order_id}", headers=headers, json={"is_on_hold": False}
    )
    assert bypass.status_code == 400
    current = await detail(db, order_id)
    assert current["is_on_hold"]
    with pytest.raises(OrderWaitingError) as blocked:
        await OrderWaitingService.execute(
            db,
            order_id,
            Command(action="resume", expected_revision=current["workflow_revision"]),
            auth=ACTOR,
            tenant_scope=TenantScope(tenant_id=1, storefront_id=1, demo_read_only=True),
        )
    assert blocked.value.status_code == 403


@pytest.mark.asyncio
async def test_foreign_order_is_indistinguishable_from_missing_and_closed_order_cannot_wait(
    db,
):
    from models import Tenant, Storefront

    tenant = Tenant(slug="foreign-waiting", display_name="Foreign")
    db.add(tenant)
    await db.flush()
    site = Storefront(
        tenant_id=tenant.id,
        slug="foreign-waiting",
        display_name="Foreign",
        status="active",
    )
    db.add(site)
    await db.flush()
    foreign = Order(tenant_id=tenant.id, storefront_id=site.id, status="execution")
    closed = Order(tenant_id=1, storefront_id=1, status="closed")
    db.add_all([foreign, closed])
    await db.commit()
    foreign_id, closed_id = foreign.id, closed.id
    with pytest.raises(OrderWaitingError) as inaccessible:
        await command(
            db, foreign_id, action="wait", expected_revision=0, reason_code="next_stage"
        )
    assert inaccessible.value.status_code == 404
    with pytest.raises(OrderWaitingError) as business:
        await command(
            db, closed_id, action="wait", expected_revision=0, reason_code="next_stage"
        )
    assert business.value.status_code == 409


@pytest.mark.asyncio
async def test_additive_migration_preserves_legacy_waiting_and_unknown_start(db):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text

    order_id = await seed(db, is_on_hold=True, on_hold_reason="Legacy waiting retained")
    connection = await db.connection()
    for name in ("workflow_revision", "on_hold_reason_code", "on_hold_started_at"):
        await connection.execute(text(f'ALTER TABLE "order" DROP COLUMN {name}'))

    def upgrade(sync_connection):
        path = (
            Path(__file__).resolve().parents[2]
            / "alembic/versions/kan20261022wait01_order_waiting.py"
        )
        spec = importlib.util.spec_from_file_location("waiting_migration", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with Operations.context(MigrationContext.configure(sync_connection)):
            module.upgrade()

    await connection.run_sync(upgrade)
    row = (
        (
            await connection.execute(
                text(
                    'SELECT is_on_hold,on_hold_reason,on_hold_reason_code,on_hold_started_at,workflow_revision FROM "order" WHERE id=:id'
                ),
                {"id": order_id},
            )
        )
        .mappings()
        .one()
    )
    assert row == {
        "is_on_hold": True,
        "on_hold_reason": "Legacy waiting retained",
        "on_hold_reason_code": None,
        "on_hold_started_at": None,
        "workflow_revision": 0,
    }


@pytest.mark.asyncio
async def test_reentrant_stage_payment_commands_advance_the_same_parent_revision(db):
    from services.command_transaction import command_transaction
    order_id = await seed(db, is_on_hold=True, on_hold_reason="Next visit")
    original = await detail(db, order_id)
    async with command_transaction(db):
        staged = await OrderWorkStageCommandService.add_order_stage(db, order_id,
            OrderWorkStageCreatePayload(name="Nested visit", status="planned"), tenant_scope=SCOPE)
        await OrderPaymentCommandService.add_payment(db, order_id,
            PaymentCreatePayload(amount=100, currency="BYN", type="prepayment"), tenant_scope=SCOPE)
        current = await detail(db, order_id)
        assert current["workflow_revision"] > staged["workflow_revision"] > original["workflow_revision"]
    latest = await detail(db, order_id)
    assert latest["workflow_revision"] == current["workflow_revision"] and latest["is_on_hold"]
    resumed = await command(db, order_id, action="resume", expected_revision=latest["workflow_revision"])
    assert resumed["workflow_revision"] > latest["workflow_revision"] and not resumed["is_on_hold"]
