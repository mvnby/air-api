"""Quick intake remains readable beyond the temporary draft lifetime."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import select

from core.command_actor import CommandActor
from models import Lead, Order, StaffUser, TenantMembership
from models.personal_task import PersonalTask
from models.tenancy import TenantScope
from schemas_incoming import IncomingCreatePayload
from services.incoming_command_service import IncomingCommandService
from services.personal_task_service import PersonalTaskService


@pytest.mark.asyncio
async def test_incoming_and_linked_task_survive_24_hours_and_recreated_engine(db_engine):
    source = datetime(2025, 12, 31, 20, 59, tzinfo=timezone.utc)
    original = (
        "  ТО квартиры +375291234567, район Билево, завтра 09:00;\n"
        "адрес уточнить; созвониться перед выездом  "
    )
    aged_at = datetime.now(timezone.utc) - timedelta(hours=25)
    writer_engine = create_async_engine(db_engine.url)
    try:
        async with AsyncSession(writer_engine, expire_on_commit=False) as session:
            staff = StaffUser(
                display_name="Persistent intake", username="persistent-intake",
                roles=["manager"], primary_role="manager",
            )
            session.add(staff)
            await session.flush()
            session.add(TenantMembership(
                tenant_id=1, staff_user_id=staff.id, role="manager", status="active",
            ))
            await session.commit()
            caller = CommandActor(staff.id, staff.username, TenantScope(1, 1), "manager")
            saved = await IncomingCommandService.create(
                session, actor=caller,
                payload=IncomingCreatePayload(
                    request_text=original, region_text="Билево",
                    source_occurred_at=source, source_timezone="Europe/Minsk",
                    source_event_id="persistent-message-1",
                ),
                idempotency_key="persistent-incoming-0001",
            )
            lead = await session.get(Lead, saved.value.lead_id)
            task = await session.get(PersonalTask, saved.value.clarification_task_id)
            lead.created_at = aged_at.replace(tzinfo=None)
            task.created_at = aged_at
            session.add_all([lead, task])
            await session.commit()
            stored_task = await PersonalTaskService.get(
                session, actor=caller, task_id=task.id,
            )
            task_snapshot = stored_task.model_dump(mode="json")
            writer_pid = (await session.execute(text("SELECT pg_backend_pid()"))).scalar_one()
    finally:
        await writer_engine.dispose()

    # The writer's session and connection pool are gone. Read through a new
    # engine to exercise persistent storage without their identity maps/caches.
    reader_engine = create_async_engine(db_engine.url)
    try:
        async with AsyncSession(reader_engine) as session:
            reader_pid = (await session.execute(text("SELECT pg_backend_pid()"))).scalar_one()
            assert reader_pid != writer_pid
            current = await IncomingCommandService.get(
                session, actor=caller, lead_id=saved.value.lead_id,
            )
            assert current.model_dump(mode="json") == saved.value.model_dump(mode="json")
            assert current.original_text == current.request_text == original
            assert current.phone == "+375291234567" and current.address_text is None
            assert current.intake_state == "needs_details"
            assert current.source_occurred_at == source
            assert current.source_timezone == "Europe/Minsk"
            assert current.requested_at.isoformat() == "2026-01-01T09:00:00+03:00"
            incoming_list = await IncomingCommandService.list(session, actor=caller)
            assert [item.lead_id for item in incoming_list.items] == [current.lead_id]
            task = await PersonalTaskService.get(
                session, actor=caller, task_id=current.clarification_task_id,
            )
            assert task.model_dump(mode="json") == task_snapshot
            assert task.lead_id == current.lead_id
            assert task.due_at is task.reminder_at is None
            tasks = await PersonalTaskService.list(session, actor=caller)
            assert [item.id for item in tasks.items] == [task.id]
            lead = await session.get(Lead, current.lead_id)
            assert datetime.now(timezone.utc) - lead.created_at.replace(tzinfo=timezone.utc) > timedelta(hours=24)
            assert datetime.now(timezone.utc) - task.created_at > timedelta(hours=24)
            assert (await session.execute(select(func.count()).select_from(Order))).scalar_one() == 0
    finally:
        await reader_engine.dispose()
