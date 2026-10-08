"""Save incomplete requests independently of parsing, orders and scheduling."""

import hashlib
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.command_actor import CommandActor
from core.config import settings
from crud.incoming_event import IncomingEventDAO
from models import Lead, LeadIntakeSource, LeadStatus
from models.leads_inbox import InboxTriageState
from schemas_incoming import (
    IncomingCreatePayload,
    IncomingClarificationPayload,
    IncomingListResponse,
    IncomingResponse,
    IncomingPreview,
    IncomingUpdatePayload,
)
from schemas_manager_leads import LeadCreatePayload
from schemas_personal_tasks import PersonalTaskCreatePayload
from services.authenticated_command_service import AuthenticatedCommandService
from services.bot_quick_order_service import BotQuickOrderService
from services.lead_command_service import LeadCommandService
from services.order_scenarios import resolve_scenario
from services.incoming_preview import incoming_preview
from services.incoming_requested_date import requested_date
from services.incoming_agreements import CLARIFICATION_TITLE, explicit_instructions
from services.personal_task_service import PersonalTaskService
from services.public_write_idempotency_service import (
    PublicWriteCommandResponse,
    PublicWriteIdempotencyConflict,
)
from services.tenant_entity_access_service import TenantEntityAccessService


class IncomingVersionConflict(ValueError):
    pass


class IncomingCommandService:
    @staticmethod
    def _fingerprint(payload):
        data = payload.model_dump(mode="json", exclude_unset=True)
        return hashlib.sha256(
            json.dumps(
                data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()

    @staticmethod
    def _fields(payload, source_time):
        fields = payload.model_dump(
            mode="json",
            include={
                "region_text",
                "workflow_type",
                "service_type",
                "address_text",
                "requested_time_text",
                "requested_at",
                "call_before_visit",
                "clarification_requested",
            },
        )
        fields["workflow_type"], fields["service_type"] = resolve_scenario(
            workflow_type=payload.workflow_type, service_type=payload.service_type,
        )
        sources = {key: "provided" for key, value in fields.items() if value is not None}
        clarification, call = explicit_instructions(payload.request_text)
        for key, inferred in (("clarification_requested", clarification), ("call_before_visit", call)):
            if fields[key] is None and inferred:
                fields[key] = True
                sources[key] = "text"
        phone = payload.phone
        if not phone and (
            isinstance(payload, IncomingCreatePayload)
            or "phone" not in payload.model_fields_set
        ):
            phone = BotQuickOrderService.normalize_phone(
                BotQuickOrderService._extract_phone(payload.request_text)
            )
            if phone:
                sources["phone"] = "text"
        elif phone:
            sources["phone"] = "provided"
        # The deterministic parser returns suggestions only. A wished-for date
        # is never a work stage or a reserved calendar slot.
        precision = "datetime" if payload.requested_at else None
        if (
            not payload.requested_at
            and (
                isinstance(payload, IncomingCreatePayload)
                or "requested_at" not in payload.model_fields_set
            )
            and source_time is not None
        ):
            parsed, precision = requested_date(
                payload.requested_time_text or payload.request_text, source_time,
                region_text=payload.region_text,
            )
            if parsed:
                fields["requested_at"] = parsed.isoformat()
                sources["requested_at"] = "text"
        fields["date_precision"] = precision
        fields["field_sources"] = sources
        return phone, fields

    @classmethod
    def _updated_meta(cls, payload, meta, source_time):
        """Omitted fields retain their values; explicit null clears them."""
        changes = payload.model_dump(mode="json", exclude_unset=True)
        updated = dict(meta)
        if {"workflow_type", "service_type"} & changes.keys():
            workflow = changes.get("workflow_type", meta.get("workflow_type"))
            service = changes.get("service_type", meta.get("service_type"))
            # A null workflow clears the scenario, while a null service keeps
            # generic work. Clear a non-generic workflow with its sole service
            # when it was omitted, rather than silently reinferring the cleared value.
            if "workflow_type" in changes and workflow is None and "service_type" not in changes:
                service = None
            if "service_type" in changes and service is None and workflow != "service_work":
                if "workflow_type" in changes and workflow is not None:
                    raise ValueError("Cleared service_type conflicts with workflow_type")
                workflow = None
            changes["workflow_type"], changes["service_type"] = resolve_scenario(
                workflow_type=workflow, service_type=service,
            )
        sources = dict(meta.get("field_sources", {}))
        changed_meta_fields = set()
        for key in (
            "name",
            "phone",
            "email",
            "region_text",
            "workflow_type",
            "service_type",
            "address_text",
            "requested_time_text",
            "requested_at",
            "call_before_visit",
            "clarification_requested",
        ):
            if key not in changes:
                continue
            if key not in {"name", "phone", "email"}:
                old_value = meta.get(key)
                new_value = changes[key]
                if key == "requested_at" and old_value and new_value:
                    same_value = datetime.fromisoformat(old_value) == datetime.fromisoformat(new_value)
                else:
                    same_value = old_value == new_value
                if same_value:
                    continue
                updated[key] = changes[key]
                changed_meta_fields.add(key)
            if changes[key] is not None:
                sources[key] = "provided"
            else:
                sources.pop(key, None)
        if "requested_at" in changes:
            if "requested_at" in changed_meta_fields:
                updated["date_precision"] = "datetime" if payload.requested_at else None
        elif "requested_time_text" in changed_meta_fields:
            # A changed wish invalidates the old suggestion. Reinterpret it only
            # against the retained source clock, never against processing time.
            updated["requested_at"] = None
            updated["date_precision"] = None
            sources.pop("requested_at", None)
            if payload.requested_time_text and source_time is not None:
                _, inferred = cls._fields(payload, source_time)
                updated["requested_at"] = inferred["requested_at"]
                updated["date_precision"] = inferred["date_precision"]
                if inferred["requested_at"]:
                    sources["requested_at"] = "text"
        updated["field_sources"] = sources
        return updated

    @staticmethod
    def _response(lead: Lead) -> IncomingResponse:
        meta = lead.intake_meta or {}
        missing = ([] if lead.phone or lead.email else ["contact"]) + (
            [] if meta.get("address_text") else ["address"]
        )
        state = (
            "needs_contact"
            if "contact" in missing
            else "needs_details"
            if missing
            else "ready_for_review"
        )
        return IncomingResponse(
            lead_id=lead.id,
            version=lead.version,
            request_text=lead.request_text,
            name=lead.name,
            phone=lead.phone,
            email=lead.email,
            region_text=meta.get("region_text"),
            workflow_type=meta.get("workflow_type"),
            service_type=meta.get("service_type"),
            address_text=meta.get("address_text"),
            requested_time_text=meta.get("requested_time_text"),
            requested_at=meta.get("requested_at"),
            intake_state=state,
            missing_fields=missing,
            source_occurred_at=meta.get("source_occurred_at"),
            source_timezone=meta.get("source_timezone", "Europe/Minsk"),
            original_text=meta.get("original_text", lead.request_text),
            date_precision=meta.get("date_precision"),
            field_sources=meta.get("field_sources", {}),
            call_before_visit=meta.get("call_before_visit"),
            clarification_requested=meta.get("clarification_requested"),
            clarification_task_id=meta.get("clarification_task_id"),
            manager_url=f"{settings.MANAGER_BASE_URL.rstrip('/')}/leads?incomingId={lead.id}",
        )

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        *,
        actor: CommandActor,
        payload: IncomingCreatePayload,
        idempotency_key: str,
    ):
        event = payload.source_event_id or idempotency_key
        event_key = hashlib.sha256(
            f"{actor.tenant_scope.tenant_id}:{actor.tenant_scope.storefront_id}:{actor.staff_user_id}:{actor.channel}:{event}".encode()
        ).hexdigest()
        fingerprint = cls._fingerprint(payload)

        async def operation():
            await IncomingEventDAO.lock_source(session, event_key)
            existing = await IncomingEventDAO.get_by_key(session, event_key)
            if existing:
                if (existing.intake_meta or {}).get(
                    "ingestion_fingerprint"
                ) != fingerprint:
                    raise PublicWriteIdempotencyConflict(
                        "Source event already saved; use its ID and current version to correct it"
                    )
                return PublicWriteCommandResponse(
                    value=cls._response(existing),
                    resource_type="lead",
                    resource_id=existing.id,
                    response_max_bytes=128 * 1024,
                )
            source_time = (
                payload.source_occurred_at.astimezone(ZoneInfo(payload.source_timezone))
                if payload.source_occurred_at
                else None
            )
            phone, fields = cls._fields(payload, source_time)
            data = await LeadCommandService.create_lead(
                session,
                LeadCreatePayload(
                    source=LeadIntakeSource.manager.value,
                    request_text=payload.request_text,
                    name=payload.name,
                    phone=phone,
                    email=payload.email,
                    source_message_id=payload.source_event_id,
                ),
                tenant_scope=actor.tenant_scope,
            )
            lead = await TenantEntityAccessService.get_lead(
                session, data["id"], tenant_scope=actor.tenant_scope
            )
            lead.request_text = payload.request_text
            lead.intake_event_key = event_key
            lead.intake_meta = {
                **fields,
                "channel": actor.channel,
                "author_id": actor.staff_user_id,
                "source_occurred_at": source_time.isoformat() if source_time else None,
                "source_timezone": payload.source_timezone,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "original_text": payload.request_text,
                "ingestion_fingerprint": fingerprint,
            }
            session.add(lead)
            await session.flush()
            if lead.intake_meta.get("clarification_requested"):
                await cls._ensure_clarification(session, actor=actor, lead=lead)
            return PublicWriteCommandResponse(
                value=cls._response(lead),
                status_code=201,
                resource_type="lead",
                resource_id=lead.id,
                response_max_bytes=128 * 1024,
            )

        return await AuthenticatedCommandService.execute(
            session,
            actor=actor,
            command_name="incoming.create",
            idempotency_key=idempotency_key,
            payload=payload,
            response_model=IncomingResponse,
            operation=operation,
        )

    @classmethod
    async def update(
        cls,
        session: AsyncSession,
        *,
        actor: CommandActor,
        lead_id: int,
        payload: IncomingUpdatePayload,
        idempotency_key: str,
    ):
        # Include the target in the fingerprint so reusing a key cannot silently
        # apply a correction to another request.
        async def operation():
            lead = await TenantEntityAccessService.get_lead(
                session,
                lead_id,
                tenant_scope=actor.tenant_scope,
                for_update=True,
                populate_existing=True,
            )
            if not lead or not lead.intake_meta:
                raise LookupError("Incoming request not found")
            state = await session.get(
                InboxTriageState, ("lead", lead_id), populate_existing=True
            )
            if (
                lead.converted_order_id is not None
                or lead.archived_at is not None
                or lead.status not in (LeadStatus.new, LeadStatus.contacted)
                or (state and state.archived_at)
            ):
                raise IncomingVersionConflict(
                    "Incoming request is archived or qualified; use its current workflow"
                )
            if lead.version != payload.expected_version:
                raise IncomingVersionConflict(
                    "Incoming request has changed; reload its current version"
                )
            meta = dict(lead.intake_meta)
            source_time = (
                datetime.fromisoformat(meta["source_occurred_at"]).astimezone(
                    ZoneInfo(meta["source_timezone"])
                )
                if meta.get("source_occurred_at")
                else None
            )
            for key in ("name", "phone", "email"):
                if key in payload.model_fields_set:
                    setattr(lead, key, getattr(payload, key))
            lead.request_text = payload.request_text
            lead.intake_meta = cls._updated_meta(payload, meta, source_time)
            if payload.clarification_requested:
                await cls._ensure_clarification(session, actor=actor, lead=lead)
            lead.version += 1
            session.add(lead)
            await session.flush()
            return PublicWriteCommandResponse(
                value=cls._response(lead),
                resource_type="lead",
                resource_id=lead.id,
                response_max_bytes=128 * 1024,
            )

        return await AuthenticatedCommandService.execute(
            session,
            actor=actor,
            command_name="incoming.update",
            idempotency_key=idempotency_key,
            payload={
                "lead_id": lead_id,
                **payload.model_dump(mode="json", exclude_unset=True),
            },
            response_model=IncomingResponse,
            operation=operation,
        )

    @staticmethod
    async def _ensure_clarification(
        session: AsyncSession, *, actor: CommandActor, lead: Lead,
    ) -> None:
        if (lead.intake_meta or {}).get("clarification_task_id"):
            return
        meta = lead.intake_meta or {}
        context = [f"Входящее #{lead.id}"]
        for label, value in (
            ("Имя", lead.name),
            ("Телефон", lead.phone),
            ("Email", lead.email),
            ("Район", meta.get("region_text")),
            ("Адрес", meta.get("address_text")),
            ("Пожелание по времени (выезд не подтверждён)", meta.get("requested_at") or meta.get("requested_time_text")),
        ):
            if value:
                context.append(f"{label}: {value}")
        if meta.get("call_before_visit"):
            context.append("Договорённость: созвониться перед выездом")
        context.append(f"Исходные сведения доступны во входящем #{lead.id}.")
        context.append(f"Текст обращения: {lead.request_text[:4000]}")
        task = await PersonalTaskService.create(
            session, actor=actor,
            payload=PersonalTaskCreatePayload(
                text=CLARIFICATION_TITLE,
                description="\n".join(context),
                lead_id=lead.id,
            ),
            idempotency_key=f"incoming-clarification-{lead.id}",
        )
        lead.intake_meta = {**meta, "clarification_task_id": task.value.id}
        session.add(lead)
        await session.flush()

    @classmethod
    async def create_clarification(
        cls,
        session: AsyncSession,
        *,
        actor: CommandActor,
        lead_id: int,
        payload: IncomingClarificationPayload,
        idempotency_key: str,
    ):
        async def operation():
            lead = await TenantEntityAccessService.get_lead(
                session, lead_id, tenant_scope=actor.tenant_scope,
                for_update=True, populate_existing=True,
            )
            if not lead or not lead.intake_meta:
                raise LookupError("Incoming request not found")
            state = await session.get(InboxTriageState, ("lead", lead_id), populate_existing=True)
            if (
                lead.version != payload.expected_version
                or lead.converted_order_id
                or lead.archived_at
                or lead.status not in (LeadStatus.new, LeadStatus.contacted)
                or (state and state.archived_at)
            ):
                raise IncomingVersionConflict("Incoming request has changed; reload its current version")
            if not lead.intake_meta.get("clarification_task_id"):
                await cls._ensure_clarification(session, actor=actor, lead=lead)
                lead.version += 1
                session.add(lead)
                await session.flush()
            return PublicWriteCommandResponse(
                value=cls._response(lead), resource_type="lead", resource_id=lead.id,
                response_max_bytes=128 * 1024,
            )
        return await AuthenticatedCommandService.execute(
            session, actor=actor, command_name="incoming.clarification",
            idempotency_key=idempotency_key,
            payload={"lead_id": lead_id, **payload.model_dump(mode="json")},
            response_model=IncomingResponse, operation=operation,
        )

    @classmethod
    async def get(cls, session: AsyncSession, *, actor: CommandActor, lead_id: int, include_preview: bool = False):
        lead = await TenantEntityAccessService.get_lead(
            session, lead_id, tenant_scope=actor.tenant_scope, populate_existing=True
        )
        if not lead or not lead.intake_meta:
            raise LookupError("Incoming request not found")
        response = cls._response(lead)
        if include_preview:
            try:
                response.preview = incoming_preview(lead.request_text)
            except Exception:
                # Suggestions are optional and cannot undo an acknowledged save.
                response.preview = IncomingPreview(state="unavailable")
        return response

    @classmethod
    async def list(
        cls,
        session: AsyncSession,
        *,
        actor: CommandActor,
        limit: int = 30,
        offset: int = 0,
    ):
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("Invalid pagination")
        archived = select(InboxTriageState.entity_id).where(
            InboxTriageState.entity_kind == "lead",
            InboxTriageState.tenant_id == actor.tenant_scope.tenant_id,
            InboxTriageState.storefront_id == actor.tenant_scope.storefront_id,
            InboxTriageState.archived_at.is_not(None),
        )
        conditions = (
            TenantEntityAccessService.lead_clause(actor.tenant_scope),
            Lead.intake_event_key.is_not(None),
            Lead.converted_order_id.is_(None),
            Lead.archived_at.is_(None),
            Lead.status.in_([LeadStatus.new, LeadStatus.contacted]),
            Lead.id.not_in(archived),
        )
        rows = (
            (
                await session.execute(
                    select(Lead)
                    .where(*conditions)
                    .order_by(Lead.created_at.desc(), Lead.id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        total = (
            await session.execute(
                select(func.count()).select_from(Lead).where(*conditions)
            )
        ).scalar_one()
        return IncomingListResponse(
            items=[cls._response(lead) for lead in rows], total=total
        )
