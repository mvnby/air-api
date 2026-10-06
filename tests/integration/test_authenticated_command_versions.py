"""Concurrent commands must bypass stale ORM objects in a reused session."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.command_actor import CommandActor
from models import Lead, StaffUser
from models.personal_task import PersonalTask
from models.tenancy import TenantMembership, TenantScope
from schemas_incoming import IncomingCreatePayload, IncomingUpdatePayload
from schemas_personal_tasks import PersonalTaskCreatePayload, PersonalTaskUpdatePayload
from services.incoming_command_service import (
    IncomingCommandService,
    IncomingVersionConflict,
)
from services.personal_task_service import (
    PersonalTaskService,
    PersonalTaskVersionConflictError,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["incoming", "task"])
async def test_reused_session_refreshes_version_and_rejects_stale_update(
    db_engine, kind
):
    async with AsyncSession(db_engine, expire_on_commit=False) as setup:
        user = StaffUser(
            display_name="Version test",
            username="version-reader",
            primary_role="manager",
            roles=["manager"],
        )
        setup.add(user)
        await setup.flush()
        setup.add(TenantMembership(tenant_id=1, staff_user_id=user.id, role="manager"))
        await setup.commit()
        actor = CommandActor(user.id, user.username, TenantScope(1, 1), "chatgpt")
        if kind == "incoming":
            service, model = IncomingCommandService, Lead
            original = await service.create(
                setup,
                actor=actor,
                payload=IncomingCreatePayload(request_text="Original incoming"),
                idempotency_key="version-create-incoming1",
            )
            record_id = original.value.lead_id
            target = {"lead_id": record_id}
            conflict = IncomingVersionConflict
        else:
            service, model = PersonalTaskService, PersonalTask
            original = await service.create(
                setup,
                actor=actor,
                payload=PersonalTaskCreatePayload(text="Original task"),
                idempotency_key="version-create-task-0001",
            )
            record_id = original.value.id
            target = {"task_id": record_id}
            conflict = PersonalTaskVersionConflictError
        version = original.value.version

    async with AsyncSession(db_engine, expire_on_commit=False) as reader:
        cached = await reader.get(model, record_id)
        assert cached.version == version
        initial = await service.get(reader, actor=actor, **target)
        assert initial.version == version

        async with AsyncSession(db_engine, expire_on_commit=False) as writer:
            payload = (
                IncomingUpdatePayload(
                    expected_version=version, request_text="Concurrent incoming change"
                )
                if kind == "incoming"
                else PersonalTaskUpdatePayload(
                    expected_version=version, text="Concurrent task change"
                )
            )
            committed = await service.update(
                writer,
                actor=actor,
                **target,
                payload=payload,
                idempotency_key="version-concurrent-change1",
            )
            assert not writer.in_transaction()
            assert committed.value.version == version + 1

        # Keep the old ORM object alive so the identity map cannot drop it. The
        # read must update this cached instance after another connection commits.
        assert cached.version == version
        refreshed = await service.get(reader, actor=actor, **target)
        assert refreshed.version == cached.version == version + 1
        assert refreshed.model_dump() == committed.value.model_dump()
        stale_payload = (
            IncomingUpdatePayload(
                expected_version=version, request_text="Stale overwrite"
            )
            if kind == "incoming"
            else PersonalTaskUpdatePayload(
                expected_version=version, text="Stale overwrite"
            )
        )
        with pytest.raises(conflict):
            await service.update(
                reader,
                actor=actor,
                **target,
                payload=stale_payload,
                idempotency_key="version-stale-overwrite1",
            )
        after = await service.get(reader, actor=actor, **target)
        assert after.model_dump() == committed.value.model_dump()
