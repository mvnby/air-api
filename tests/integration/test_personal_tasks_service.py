from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import select

from core.command_actor import CommandActor
from models import (
    Customer,
    CustomerEquipment,
    Lead,
    Order,
    StaffUser,
    Storefront,
    Tenant,
    TenantMembership,
)
from models.personal_task import PersonalTask
from models.tenancy import TenantScope
from schemas_personal_tasks import (
    PersonalTaskCreatePayload,
    PersonalTaskStatusPayload,
    PersonalTaskUpdatePayload,
)
from services.personal_task_service import (
    PersonalTaskNotFoundError,
    PersonalTaskService,
    PersonalTaskVersionConflictError,
)
from services.public_write_idempotency_service import PublicWriteIdempotencyConflict


async def _actor(db, *, username: str = "task-owner") -> CommandActor:
    staff = StaffUser(
        display_name="Автор поручений",
        username=username,
        status="active",
        roles=["manager"],
        primary_role="manager",
    )
    db.add(staff)
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=1,
            staff_user_id=int(staff.id),
            role="manager",
            status="active",
        )
    )
    await db.commit()
    return CommandActor(
        staff_user_id=int(staff.id),
        username=username,
        tenant_scope=TenantScope(
            tenant_id=1,
            storefront_id=1,
            is_system=True,
        ),
        channel="manager",
    )


@pytest.mark.asyncio
async def test_personal_task_text_only_is_persistent_and_idempotent(db):
    actor = await _actor(db)
    payload = PersonalTaskCreatePayload(text="  Дослать коммерческое   предложение ")

    created = await PersonalTaskService.create(
        db,
        actor=actor,
        payload=payload,
        idempotency_key="personal-task-create-0001",
    )
    replayed = await PersonalTaskService.create(
        db,
        actor=actor,
        payload=payload,
        idempotency_key="personal-task-create-0001",
    )

    assert created.status_code == 201
    assert created.replayed is False
    assert created.value.text == "Дослать коммерческое предложение"
    assert created.value.assignee_staff_user_id == actor.staff_user_id
    assert replayed.replayed is True
    assert replayed.value.id == created.value.id
    tasks = list((await db.execute(select(PersonalTask))).scalars().all())
    assert [task.id for task in tasks] == [created.value.id]

    with pytest.raises(PublicWriteIdempotencyConflict):
        await PersonalTaskService.create(
            db,
            actor=actor,
            payload=PersonalTaskCreatePayload(text="Уже другое поручение"),
            idempotency_key="personal-task-create-0001",
        )


@pytest.mark.asyncio
async def test_personal_task_receipt_accepts_max_unicode_description(db):
    actor = await _actor(db, username="task-unicode-owner")
    description = "🧰" * 12_000

    created = await PersonalTaskService.create(
        db,
        actor=actor,
        payload=PersonalTaskCreatePayload(
            text="Сохранить подробное поручение",
            description=description,
        ),
        idempotency_key="personal-task-unicode-0001",
    )
    replayed = await PersonalTaskService.create(
        db,
        actor=actor,
        payload=PersonalTaskCreatePayload(
            text="Сохранить подробное поручение",
            description=description,
        ),
        idempotency_key="personal-task-unicode-0001",
    )

    assert created.value.description == description
    assert replayed.replayed is True
    assert replayed.value.description == description


@pytest.mark.asyncio
async def test_personal_task_visibility_is_limited_to_author_or_assignee(db):
    author = await _actor(db, username="task-visibility-author")
    outsider = await _actor(db, username="task-visibility-outsider")
    private = await PersonalTaskService.create(
        db,
        actor=author,
        payload=PersonalTaskCreatePayload(text="Личное поручение"),
        idempotency_key="personal-task-private-0001",
    )

    outsider_list = await PersonalTaskService.list(db, actor=outsider)
    assert outsider_list.items == []
    with pytest.raises(PersonalTaskNotFoundError):
        await PersonalTaskService.get(
            db,
            actor=outsider,
            task_id=private.value.id,
        )

    assigned = await PersonalTaskService.create(
        db,
        actor=author,
        payload=PersonalTaskCreatePayload(
            text="Назначенное поручение",
            assignee_staff_user_id=outsider.staff_user_id,
        ),
        idempotency_key="personal-task-assigned-0001",
    )
    outsider_list = await PersonalTaskService.list(db, actor=outsider)
    assert [item.id for item in outsider_list.items] == [assigned.value.id]


@pytest.mark.asyncio
async def test_personal_task_versions_filters_and_query_time_reminders(db):
    actor = await _actor(db, username="task-reminder-owner")
    now = datetime.now(timezone.utc)
    created = await PersonalTaskService.create(
        db,
        actor=actor,
        payload=PersonalTaskCreatePayload(
            text="Перезвонить клиенту",
            reminder_at=now - timedelta(minutes=5),
        ),
        idempotency_key="personal-task-reminder-0001",
    )
    task = created.value

    active = await PersonalTaskService.list(
        db,
        actor=actor,
        task_filter="undated",
        reference_time=now,
    )
    assert [item.id for item in active.items] == [task.id]
    assert active.items[0].reminder_due is True
    assert active.due_reminder_count == 1

    rescheduled = await PersonalTaskService.update(
        db,
        actor=actor,
        task_id=task.id,
        payload=PersonalTaskUpdatePayload(
            expected_version=task.version,
            reminder_at=now + timedelta(hours=2),
        ),
        idempotency_key="personal-task-reminder-reschedule-0001",
    )
    assert rescheduled.value.reminder_due is False
    assert rescheduled.value.version == 2
    rescheduled_replay = await PersonalTaskService.update(
        db,
        actor=actor,
        task_id=task.id,
        payload=PersonalTaskUpdatePayload(
            expected_version=task.version,
            reminder_at=now + timedelta(hours=2),
        ),
        idempotency_key="personal-task-reminder-reschedule-0001",
    )
    assert rescheduled_replay.replayed is True
    assert rescheduled_replay.value.version == 2
    after_reschedule = await PersonalTaskService.list(
        db,
        actor=actor,
        task_filter="active",
        reference_time=now,
    )
    assert after_reschedule.due_reminder_count == 0

    with pytest.raises(PersonalTaskVersionConflictError):
        await PersonalTaskService.update(
            db,
            actor=actor,
            task_id=task.id,
            payload=PersonalTaskUpdatePayload(
                expected_version=1,
                text="Устаревшая правка",
            ),
            idempotency_key="personal-task-stale-update-0001",
        )

    completed = await PersonalTaskService.complete(
        db,
        actor=actor,
        task_id=task.id,
        payload=PersonalTaskStatusPayload(expected_version=2),
        idempotency_key="personal-task-complete-0001",
    )
    assert completed.value.status == "completed"
    assert completed.value.reminder_due is False
    completed_replay = await PersonalTaskService.complete(
        db,
        actor=actor,
        task_id=task.id,
        payload=PersonalTaskStatusPayload(expected_version=2),
        idempotency_key="personal-task-complete-0001",
    )
    assert completed_replay.replayed is True
    assert completed_replay.value.version == 3
    with pytest.raises(PublicWriteIdempotencyConflict):
        await PersonalTaskService.complete(
            db,
            actor=actor,
            task_id=task.id,
            payload=PersonalTaskStatusPayload(expected_version=3),
            idempotency_key="personal-task-complete-0001",
        )
    completed_list = await PersonalTaskService.list(
        db,
        actor=actor,
        task_filter="completed",
        reference_time=now + timedelta(hours=3),
    )
    assert [item.id for item in completed_list.items] == [task.id]
    assert completed_list.due_reminder_count == 0

    reopened = await PersonalTaskService.reopen(
        db,
        actor=actor,
        task_id=task.id,
        payload=PersonalTaskStatusPayload(expected_version=3),
        idempotency_key="personal-task-reopen-0001",
    )
    assert reopened.value.status == "active"
    assert reopened.value.version == 4


@pytest.mark.asyncio
async def test_personal_task_rejects_foreign_assignee_and_links(db):
    actor = await _actor(db, username="task-scope-owner")
    foreign_tenant = Tenant(
        slug="personal-task-foreign",
        display_name="Foreign",
        kind="partner",
        status="active",
        is_system=False,
    )
    db.add(foreign_tenant)
    await db.flush()
    foreign_storefront = Storefront(
        tenant_id=int(foreign_tenant.id),
        slug="main",
        display_name="Foreign main",
        status="active",
        is_default=True,
    )
    foreign_staff = StaffUser(
        display_name="Чужой сотрудник",
        username="foreign-task-staff",
        status="active",
        roles=["manager"],
        primary_role="manager",
    )
    foreign_customer = Customer(
        tenant_id=int(foreign_tenant.id),
        name="Чужой клиент",
        phone="+375291234567",
    )
    db.add_all([foreign_storefront, foreign_staff, foreign_customer])
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=int(foreign_tenant.id),
            staff_user_id=int(foreign_staff.id),
            role="manager",
            status="active",
        )
    )
    equipment = CustomerEquipment(customer_id=int(foreign_customer.id))
    db.add(equipment)

    other_storefront = Storefront(
        tenant_id=1,
        slug="personal-task-other",
        display_name="Other storefront",
        status="active",
        is_default=False,
    )
    db.add(other_storefront)
    await db.flush()
    foreign_lead = Lead(
        tenant_id=1,
        storefront_id=int(other_storefront.id),
        source="manager",
        request_text="Чужое входящее",
    )
    foreign_order = Order(
        tenant_id=1,
        storefront_id=int(other_storefront.id),
        status="negotiation",
    )
    db.add_all([foreign_lead, foreign_order])
    await db.commit()

    rejected_payloads = (
        PersonalTaskCreatePayload(
            text="Чужой исполнитель",
            assignee_staff_user_id=int(foreign_staff.id),
        ),
        PersonalTaskCreatePayload(text="Чужой лид", lead_id=int(foreign_lead.id)),
        PersonalTaskCreatePayload(
            text="Чужой клиент",
            customer_id=int(foreign_customer.id),
        ),
        PersonalTaskCreatePayload(text="Чужой заказ", order_id=int(foreign_order.id)),
        PersonalTaskCreatePayload(
            text="Чужое оборудование",
            equipment_id=int(equipment.id),
        ),
    )
    for index, payload in enumerate(rejected_payloads):
        with pytest.raises(ValueError):
            await PersonalTaskService.create(
                db,
                actor=actor,
                payload=payload,
                idempotency_key=f"personal-task-foreign-{index:04d}",
            )
