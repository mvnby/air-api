"""Save incomplete requests independently of parsing, orders and scheduling."""

import hashlib
import json
import re
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
    IncomingListResponse,
    IncomingResponse,
    IncomingUpdatePayload,
)
from schemas_manager_leads import LeadCreatePayload
from services.authenticated_command_service import AuthenticatedCommandService
from services.bot_quick_order_service import BotQuickOrderService
from services.lead_command_service import LeadCommandService
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
                "address_text",
                "requested_time_text",
                "requested_at",
            },
        )
        sources = {key: "provided" for key, value in fields.items() if value}
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
        if (
            not payload.requested_at
            and (
                isinstance(payload, IncomingCreatePayload)
                or "requested_at" not in payload.model_fields_set
            )
            and source_time is not None
        ):
            parsed = BotQuickOrderService._parse_date(
                payload.requested_time_text or payload.request_text, now=source_time
            )
            if parsed:
                fields["requested_at"] = parsed.isoformat()
                sources["requested_at"] = "text"
        explicit_time = re.search(
            r"\b\d{1,2}:\d{2}\b|\b(?:в|к)\s*\d{1,2}\b",
            payload.requested_time_text or payload.request_text,
        )
        fields["date_precision"] = (
            ("datetime" if payload.requested_at or explicit_time else "date")
            if fields.get("requested_at")
            else None
        )
        fields["field_sources"] = sources
        return phone, fields

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
                session, lead_id, tenant_scope=actor.tenant_scope, for_update=True, populate_existing=True
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
            phone, fields = cls._fields(payload, source_time)
            lead.name, lead.phone, lead.email, lead.request_text = (
                payload.name,
                phone,
                payload.email,
                payload.request_text,
            )
            lead.intake_meta = {**meta, **fields}
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
            payload={"lead_id": lead_id, **payload.model_dump(mode="json")},
            response_model=IncomingResponse,
            operation=operation,
        )

    @classmethod
    async def get(cls, session: AsyncSession, *, actor: CommandActor, lead_id: int):
        lead = await TenantEntityAccessService.get_lead(
            session, lead_id, tenant_scope=actor.tenant_scope, populate_existing=True
        )
        if not lead or not lead.intake_meta:
            raise LookupError("Incoming request not found")
        return cls._response(lead)

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
