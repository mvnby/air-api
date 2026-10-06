"""Application service for persistent personal tasks and due reminders."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.command_actor import CommandActor
from models import StaffUser, TenantMembership
from models.personal_task import PersonalTask, utc_now
from schemas_personal_tasks import (
    PersonalTaskCreatePayload,
    PersonalTaskAssigneeListResponse,
    PersonalTaskAssigneeResponse,
    PersonalTaskListFilter,
    PersonalTaskListResponse,
    PersonalTaskResponse,
    PersonalTaskStatusPayload,
    PersonalTaskUpdatePayload,
)
from services.authenticated_command_service import AuthenticatedCommandService
from services.public_write_idempotency_service import (
    PublicWriteCommandOutcome,
    PublicWriteCommandResponse,
)
from services.staff_user_service import StaffUserService
from services.tenant_entity_access_service import TenantEntityAccessService
from services.tenant_scope_service import storefront_scope_clause


TASK_TIMEZONE = ZoneInfo("Europe/Minsk")
TASK_WRITE_RESPONSE_MAX_BYTES = 128 * 1024


class PersonalTaskNotFoundError(LookupError):
    pass


class PersonalTaskVersionConflictError(RuntimeError):
    def __init__(self, current_version: int):
        super().__init__("Поручение уже изменилось")
        self.current_version = current_version


class PersonalTaskStatusConflictError(RuntimeError):
    pass


class PersonalTaskService:
    MUTABLE_FIELDS = frozenset(
        {
            "text",
            "description",
            "assignee_staff_user_id",
            "due_at",
            "reminder_at",
            "lead_id",
            "customer_id",
            "order_id",
            "equipment_id",
        }
    )
    LIST_FILTERS = frozenset(
        {"active", "today", "overdue", "undated", "completed", "cancelled"}
    )

    @staticmethod
    def _normalize_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=TASK_TIMEZONE)
        return value.astimezone(timezone.utc)

    @classmethod
    def _normalize_create_payload(
        cls,
        payload: PersonalTaskCreatePayload,
    ) -> PersonalTaskCreatePayload:
        return payload.model_copy(
            update={
                "due_at": cls._normalize_datetime(payload.due_at),
                "reminder_at": cls._normalize_datetime(payload.reminder_at),
            }
        )

    @classmethod
    def _normalize_update_payload(
        cls,
        payload: PersonalTaskUpdatePayload,
    ) -> PersonalTaskUpdatePayload:
        updates = {
            field: cls._normalize_datetime(getattr(payload, field))
            for field in ("due_at", "reminder_at")
            if field in payload.model_fields_set
        }
        return payload.model_copy(update=updates)

    @staticmethod
    def _visible_clause(actor: CommandActor):
        return (
            storefront_scope_clause(PersonalTask, actor.tenant_scope),
            or_(
                PersonalTask.author_staff_user_id == actor.staff_user_id,
                PersonalTask.assignee_staff_user_id == actor.staff_user_id,
            ),
        )

    @classmethod
    async def _get_visible(
        cls,
        session: AsyncSession,
        *,
        actor: CommandActor,
        task_id: int,
        for_update: bool = False,
    ) -> PersonalTask:
        statement = (
            select(PersonalTask)
            .where(
                PersonalTask.id == int(task_id),
                *cls._visible_clause(actor),
            )
            .execution_options(populate_existing=True)
        )
        if for_update:
            statement = statement.with_for_update()
        task = (await session.execute(statement)).scalars().first()
        if task is None:
            raise PersonalTaskNotFoundError("Поручение не найдено")
        return task

    @staticmethod
    async def _require_assignee(
        session: AsyncSession,
        *,
        actor: CommandActor,
        staff_user_id: int | None,
    ) -> None:
        if staff_user_id is None:
            return
        row = (
            await session.execute(
                select(StaffUser.id)
                .join(
                    TenantMembership,
                    TenantMembership.staff_user_id == StaffUser.id,
                )
                .where(
                    StaffUser.id == int(staff_user_id),
                    StaffUser.status == StaffUserService.STATUS_ACTIVE,
                    TenantMembership.tenant_id == actor.tenant_scope.tenant_id,
                    TenantMembership.status == "active",
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise ValueError("Исполнитель недоступен в текущей компании")

    @staticmethod
    async def _validate_links(
        session: AsyncSession,
        *,
        actor: CommandActor,
        lead_id: int | None,
        customer_id: int | None,
        order_id: int | None,
        equipment_id: int | None,
    ) -> None:
        scope = actor.tenant_scope
        if (
            lead_id is not None
            and await TenantEntityAccessService.get_lead(
                session, lead_id, tenant_scope=scope
            )
            is None
        ):
            raise ValueError("Связанное входящее недоступно")
        if (
            customer_id is not None
            and await TenantEntityAccessService.get_customer(
                session, customer_id, tenant_scope=scope
            )
            is None
        ):
            raise ValueError("Связанный клиент недоступен")
        if (
            order_id is not None
            and await TenantEntityAccessService.get_order(
                session, order_id, tenant_scope=scope
            )
            is None
        ):
            raise ValueError("Связанный заказ недоступен")
        if (
            equipment_id is not None
            and await TenantEntityAccessService.get_equipment(
                session, equipment_id, tenant_scope=scope
            )
            is None
        ):
            raise ValueError("Связанное оборудование недоступно")

    @staticmethod
    async def _staff_names(
        session: AsyncSession,
        staff_user_ids: set[int],
    ) -> dict[int, str]:
        if not staff_user_ids:
            return {}
        rows = (
            await session.execute(
                select(StaffUser.id, StaffUser.display_name).where(
                    StaffUser.id.in_(staff_user_ids)
                )
            )
        ).all()
        return {int(staff_id): str(name) for staff_id, name in rows}

    @classmethod
    def _project(
        cls,
        task: PersonalTask,
        *,
        names: dict[int, str],
        reference_time: datetime | None = None,
    ) -> PersonalTaskResponse:
        now = reference_time or datetime.now(timezone.utc)
        reminder_at = cls._normalize_datetime(task.reminder_at)
        return PersonalTaskResponse(
            id=int(task.id or 0),
            text=task.text,
            description=task.description,
            status=task.status,
            version=task.version,
            author_staff_user_id=task.author_staff_user_id,
            author_name=names.get(task.author_staff_user_id, "Сотрудник"),
            assignee_staff_user_id=task.assignee_staff_user_id,
            assignee_name=(
                names.get(task.assignee_staff_user_id)
                if task.assignee_staff_user_id is not None
                else None
            ),
            due_at=cls._normalize_datetime(task.due_at),
            reminder_at=reminder_at,
            reminder_due=(
                task.status == "active"
                and reminder_at is not None
                and reminder_at <= now
            ),
            lead_id=task.lead_id,
            customer_id=task.customer_id,
            order_id=task.order_id,
            equipment_id=task.equipment_id,
            completed_at=cls._normalize_datetime(task.completed_at),
            cancelled_at=cls._normalize_datetime(task.cancelled_at),
            created_at=cls._normalize_datetime(task.created_at) or task.created_at,
            updated_at=cls._normalize_datetime(task.updated_at) or task.updated_at,
        )

    @classmethod
    async def _project_one(
        cls,
        session: AsyncSession,
        task: PersonalTask,
    ) -> PersonalTaskResponse:
        ids = {task.author_staff_user_id}
        if task.assignee_staff_user_id is not None:
            ids.add(task.assignee_staff_user_id)
        return cls._project(task, names=await cls._staff_names(session, ids))

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        *,
        actor: CommandActor,
        payload: PersonalTaskCreatePayload,
        idempotency_key: str,
    ) -> PublicWriteCommandOutcome[PersonalTaskResponse]:
        command_payload = cls._normalize_create_payload(payload)

        async def operation() -> PublicWriteCommandResponse[PersonalTaskResponse]:
            assignee_id = command_payload.assignee_staff_user_id or actor.staff_user_id
            await cls._require_assignee(
                session,
                actor=actor,
                staff_user_id=assignee_id,
            )
            await cls._validate_links(
                session,
                actor=actor,
                lead_id=command_payload.lead_id,
                customer_id=command_payload.customer_id,
                order_id=command_payload.order_id,
                equipment_id=command_payload.equipment_id,
            )
            now = utc_now()
            task = PersonalTask(
                tenant_id=actor.tenant_scope.tenant_id,
                storefront_id=actor.tenant_scope.storefront_id,
                author_staff_user_id=actor.staff_user_id,
                assignee_staff_user_id=assignee_id,
                text=command_payload.text,
                description=command_payload.description,
                due_at=command_payload.due_at,
                reminder_at=command_payload.reminder_at,
                lead_id=command_payload.lead_id,
                customer_id=command_payload.customer_id,
                order_id=command_payload.order_id,
                equipment_id=command_payload.equipment_id,
                created_at=now,
                updated_at=now,
            )
            session.add(task)
            await session.flush()
            response = await cls._project_one(session, task)
            return PublicWriteCommandResponse(
                value=response,
                status_code=201,
                resource_type="personal_task",
                resource_id=int(task.id or 0),
                response_max_bytes=TASK_WRITE_RESPONSE_MAX_BYTES,
            )

        return await AuthenticatedCommandService.execute(
            session,
            actor=actor,
            command_name="personal_task.create",
            idempotency_key=idempotency_key,
            payload=command_payload,
            response_model=PersonalTaskResponse,
            operation=operation,
        )

    @classmethod
    async def update(
        cls,
        session: AsyncSession,
        *,
        actor: CommandActor,
        task_id: int,
        payload: PersonalTaskUpdatePayload,
        idempotency_key: str,
    ) -> PublicWriteCommandOutcome[PersonalTaskResponse]:
        command_payload = cls._normalize_update_payload(payload)

        async def operation() -> PublicWriteCommandResponse[PersonalTaskResponse]:
            task = await cls._get_visible(
                session,
                actor=actor,
                task_id=task_id,
                for_update=True,
            )
            if task.version != command_payload.expected_version:
                raise PersonalTaskVersionConflictError(task.version)

            fields = command_payload.model_fields_set.intersection(cls.MUTABLE_FIELDS)
            next_values = {
                "assignee_staff_user_id": task.assignee_staff_user_id,
                "lead_id": task.lead_id,
                "customer_id": task.customer_id,
                "order_id": task.order_id,
                "equipment_id": task.equipment_id,
            }
            for field in next_values:
                if field in fields:
                    next_values[field] = getattr(command_payload, field)
            await cls._require_assignee(
                session,
                actor=actor,
                staff_user_id=next_values["assignee_staff_user_id"],
            )
            await cls._validate_links(
                session,
                actor=actor,
                lead_id=next_values["lead_id"],
                customer_id=next_values["customer_id"],
                order_id=next_values["order_id"],
                equipment_id=next_values["equipment_id"],
            )

            for field in fields:
                value = getattr(command_payload, field)
                setattr(task, field, value)
            task.version += 1
            task.updated_at = utc_now()
            session.add(task)
            await session.flush()
            return PublicWriteCommandResponse(
                value=await cls._project_one(session, task),
                resource_type="personal_task",
                resource_id=int(task.id or 0),
                response_max_bytes=TASK_WRITE_RESPONSE_MAX_BYTES,
            )

        return await AuthenticatedCommandService.execute(
            session,
            actor=actor,
            command_name=f"personal_task.update.{task_id}",
            idempotency_key=idempotency_key,
            payload=command_payload,
            response_model=PersonalTaskResponse,
            operation=operation,
        )

    @classmethod
    async def _change_status(
        cls,
        session: AsyncSession,
        *,
        actor: CommandActor,
        task_id: int,
        payload: PersonalTaskStatusPayload,
        idempotency_key: str,
        action: str,
    ) -> PublicWriteCommandOutcome[PersonalTaskResponse]:
        targets = {
            "complete": "completed",
            "cancel": "cancelled",
            "reopen": "active",
        }
        target = targets[action]

        async def operation() -> PublicWriteCommandResponse[PersonalTaskResponse]:
            task = await cls._get_visible(
                session,
                actor=actor,
                task_id=task_id,
                for_update=True,
            )
            if task.version != payload.expected_version:
                raise PersonalTaskVersionConflictError(task.version)
            if task.status == target:
                raise PersonalTaskStatusConflictError(
                    "Поручение уже находится в этом состоянии"
                )
            if action in {"complete", "cancel"} and task.status != "active":
                raise PersonalTaskStatusConflictError(
                    "Изменить можно только активное поручение"
                )
            if action == "reopen" and task.status == "active":
                raise PersonalTaskStatusConflictError("Поручение уже активно")

            now = utc_now()
            task.status = target
            task.completed_at = now if target == "completed" else None
            task.cancelled_at = now if target == "cancelled" else None
            task.version += 1
            task.updated_at = now
            session.add(task)
            await session.flush()
            return PublicWriteCommandResponse(
                value=await cls._project_one(session, task),
                resource_type="personal_task",
                resource_id=int(task.id or 0),
                response_max_bytes=TASK_WRITE_RESPONSE_MAX_BYTES,
            )

        return await AuthenticatedCommandService.execute(
            session,
            actor=actor,
            command_name=f"personal_task.{action}.{task_id}",
            idempotency_key=idempotency_key,
            payload=payload,
            response_model=PersonalTaskResponse,
            operation=operation,
        )

    @classmethod
    async def complete(
        cls,
        session: AsyncSession,
        *,
        actor: CommandActor,
        task_id: int,
        payload: PersonalTaskStatusPayload,
        idempotency_key: str,
    ) -> PublicWriteCommandOutcome[PersonalTaskResponse]:
        return await cls._change_status(
            session,
            actor=actor,
            task_id=task_id,
            payload=payload,
            idempotency_key=idempotency_key,
            action="complete",
        )

    @classmethod
    async def reopen(
        cls,
        session: AsyncSession,
        *,
        actor: CommandActor,
        task_id: int,
        payload: PersonalTaskStatusPayload,
        idempotency_key: str,
    ) -> PublicWriteCommandOutcome[PersonalTaskResponse]:
        return await cls._change_status(
            session,
            actor=actor,
            task_id=task_id,
            payload=payload,
            idempotency_key=idempotency_key,
            action="reopen",
        )

    @classmethod
    async def cancel(
        cls,
        session: AsyncSession,
        *,
        actor: CommandActor,
        task_id: int,
        payload: PersonalTaskStatusPayload,
        idempotency_key: str,
    ) -> PublicWriteCommandOutcome[PersonalTaskResponse]:
        return await cls._change_status(
            session,
            actor=actor,
            task_id=task_id,
            payload=payload,
            idempotency_key=idempotency_key,
            action="cancel",
        )

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        *,
        actor: CommandActor,
        task_id: int,
    ) -> PersonalTaskResponse:
        return await cls._project_one(
            session,
            await cls._get_visible(session, actor=actor, task_id=task_id),
        )

    @staticmethod
    async def list_assignees(
        session: AsyncSession,
        *,
        actor: CommandActor,
        limit: int = 100,
    ) -> PersonalTaskAssigneeListResponse:
        if not 1 <= limit <= 100:
            raise ValueError("limit должен быть от 1 до 100")
        rows = (
            await session.execute(
                select(StaffUser.id, StaffUser.display_name)
                .join(
                    TenantMembership,
                    TenantMembership.staff_user_id == StaffUser.id,
                )
                .where(
                    StaffUser.status == StaffUserService.STATUS_ACTIVE,
                    TenantMembership.tenant_id == actor.tenant_scope.tenant_id,
                    TenantMembership.status == "active",
                )
                .order_by(StaffUser.display_name.asc(), StaffUser.id.asc())
                .limit(limit)
            )
        ).all()
        return PersonalTaskAssigneeListResponse(
            items=[
                PersonalTaskAssigneeResponse(id=int(staff_id), display_name=str(name))
                for staff_id, name in rows
            ]
        )

    @classmethod
    async def list(
        cls,
        session: AsyncSession,
        *,
        actor: CommandActor,
        task_filter: PersonalTaskListFilter = "active",
        limit: int = 50,
        offset: int = 0,
        reference_time: datetime | None = None,
    ) -> PersonalTaskListResponse:
        if not 1 <= limit <= 100:
            raise ValueError("limit должен быть от 1 до 100")
        if offset < 0:
            raise ValueError("offset не может быть отрицательным")
        if task_filter not in cls.LIST_FILTERS:
            raise ValueError("Неизвестный фильтр поручений")
        now = cls._normalize_datetime(reference_time) or datetime.now(timezone.utc)
        visible = cls._visible_clause(actor)
        filters = list(visible)
        if task_filter == "active":
            filters.append(PersonalTask.status == "active")
        elif task_filter == "today":
            local_now = now.astimezone(TASK_TIMEZONE)
            local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
            start = local_start.astimezone(timezone.utc)
            end = local_start + timedelta(days=1)
            filters.extend(
                (
                    PersonalTask.status == "active",
                    PersonalTask.due_at >= start,
                    PersonalTask.due_at < end.astimezone(timezone.utc),
                )
            )
        elif task_filter == "overdue":
            filters.extend(
                (
                    PersonalTask.status == "active",
                    PersonalTask.due_at.is_not(None),
                    PersonalTask.due_at < now,
                )
            )
        elif task_filter == "undated":
            filters.extend(
                (
                    PersonalTask.status == "active",
                    PersonalTask.due_at.is_(None),
                )
            )
        else:
            filters.append(PersonalTask.status == task_filter)

        total = int(
            (
                await session.execute(
                    select(func.count(PersonalTask.id)).where(*filters)
                )
            ).scalar_one()
        )
        statement = (
            select(PersonalTask)
            .where(*filters)
            .order_by(
                PersonalTask.due_at.asc().nullslast(),
                PersonalTask.created_at.desc(),
                PersonalTask.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        tasks = list((await session.execute(statement)).scalars().all())
        ids = {item.author_staff_user_id for item in tasks}
        ids.update(
            item.assignee_staff_user_id
            for item in tasks
            if item.assignee_staff_user_id is not None
        )
        names = await cls._staff_names(session, ids)
        due_reminder_count = int(
            (
                await session.execute(
                    select(func.count(PersonalTask.id)).where(
                        *visible,
                        PersonalTask.status == "active",
                        PersonalTask.reminder_at.is_not(None),
                        PersonalTask.reminder_at <= now,
                    )
                )
            ).scalar_one()
        )
        return PersonalTaskListResponse(
            items=[
                cls._project(item, names=names, reference_time=now) for item in tasks
            ],
            total=total,
            limit=limit,
            offset=offset,
            filter=task_filter,
            due_reminder_count=due_reminder_count,
        )
