"""Transactional commands for Manager and internal Lead workflows."""

from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from models import Lead, LeadIntakeSource, LeadLossReason, LeadStatus
from services.command_transaction import command_transaction
from services.lead_service import LeadService
from services.tenant_entity_access_service import TenantEntityAccessService
from services.tenant_scope_service import TenantScope


class LeadCommandService:
    @staticmethod
    async def create_lead(
        session: AsyncSession,
        payload: Any,
        *,
        tenant_scope: TenantScope,
    ) -> Dict[str, Any]:
        async with command_transaction(session):
            request_text = (payload.request_text or "").strip()
            if not request_text:
                raise ValueError("request_text is required")

            inn = LeadService._clean_optional(payload.inn)
            segment_hint = LeadService._normalize_segment_hint(
                inn,
                payload.segment_hint,
            )
            source = LeadIntakeSource(payload.source)
            lead = Lead(
                tenant_id=tenant_scope.tenant_id,
                storefront_id=tenant_scope.storefront_id,
                status=LeadStatus.new,
                source=source,
                segment_hint=segment_hint,
                name=LeadService._clean_optional(payload.name),
                phone=LeadService._clean_optional(payload.phone),
                email=LeadService._clean_optional(payload.email),
                inn=inn,
                company_name=LeadService._clean_optional(payload.company_name),
                request_text=request_text,
                source_message_id=LeadService._clean_optional(
                    getattr(payload, "source_message_id", None)
                ),
                source_fingerprint=LeadService._clean_optional(
                    getattr(payload, "source_fingerprint", None)
                ),
                next_followup_date=LeadService._normalize_naive_datetime(
                    payload.next_followup_date
                ),
            )
            session.add(lead)
            await session.flush()

        await session.refresh(lead)
        return LeadService._map_lead(lead)

    @staticmethod
    async def update_lead(
        session: AsyncSession,
        lead_id: int,
        payload: Any,
        *,
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        async with command_transaction(session):
            lead = await TenantEntityAccessService.get_lead(
                session,
                lead_id,
                tenant_scope=tenant_scope,
                for_update=True,
            )
            if not lead:
                return None

            fields_set = getattr(payload, "model_fields_set", None)
            if fields_set is None:
                fields_set = getattr(payload, "__fields_set__", set())

            explicit_segment_hint: Optional[str] = None
            should_recompute_segment = False
            if "status" in fields_set and payload.status is not None:
                next_status = LeadStatus(payload.status)
                if next_status in {
                    LeadStatus.qualified,
                    LeadStatus.lost,
                    LeadStatus.spam,
                }:
                    raise ValueError(
                        "Use dedicated lead workflow endpoints for terminal statuses"
                    )
                lead.status = next_status
            if "source" in fields_set and payload.source is not None:
                lead.source = LeadIntakeSource(payload.source)
            if "name" in fields_set:
                lead.name = LeadService._clean_optional(payload.name)
            if "phone" in fields_set:
                lead.phone = LeadService._clean_optional(payload.phone)
            if "email" in fields_set:
                lead.email = LeadService._clean_optional(payload.email)
            if "inn" in fields_set:
                lead.inn = LeadService._clean_optional(payload.inn)
                should_recompute_segment = True
            if "company_name" in fields_set:
                lead.company_name = LeadService._clean_optional(payload.company_name)
            if "request_text" in fields_set and payload.request_text is not None:
                request_text = payload.request_text.strip()
                if not request_text:
                    raise ValueError("request_text cannot be empty")
                lead.request_text = request_text
            if "source_message_id" in fields_set:
                lead.source_message_id = LeadService._clean_optional(
                    payload.source_message_id
                )
            if "source_fingerprint" in fields_set:
                lead.source_fingerprint = LeadService._clean_optional(
                    payload.source_fingerprint
                )
            if "loss_reason" in fields_set:
                lead.loss_reason = (
                    LeadLossReason(payload.loss_reason)
                    if payload.loss_reason
                    else None
                )
            if "next_followup_date" in fields_set:
                lead.next_followup_date = LeadService._normalize_naive_datetime(
                    payload.next_followup_date
                )
            if "archived_at" in fields_set:
                lead.archived_at = LeadService._normalize_naive_datetime(
                    payload.archived_at
                )
            if "segment_hint" in fields_set:
                explicit_segment_hint = payload.segment_hint
                should_recompute_segment = True

            if should_recompute_segment:
                lead.segment_hint = LeadService._normalize_segment_hint(
                    lead.inn,
                    explicit_segment_hint,
                )

            session.add(lead)
            await session.flush()

        await session.refresh(lead)
        return LeadService._map_lead(lead)

    @staticmethod
    async def mark_lead_lost(
        session: AsyncSession,
        lead_id: int,
        payload: Any,
        *,
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        async with command_transaction(session):
            lead = await TenantEntityAccessService.get_lead(
                session,
                lead_id,
                tenant_scope=tenant_scope,
                for_update=True,
            )
            if not lead:
                return None

            next_status = LeadStatus(payload.status)
            if next_status not in {LeadStatus.lost, LeadStatus.spam}:
                raise ValueError("Lead can only be marked lost or spam here")
            lead.status = next_status
            lead.loss_reason = (
                LeadLossReason(payload.loss_reason)
                if payload.loss_reason
                else (
                    LeadLossReason.spam
                    if lead.status == LeadStatus.spam
                    else lead.loss_reason
                )
            )
            lead.next_followup_date = None
            session.add(lead)
            await session.flush()

        await session.refresh(lead)
        return LeadService._map_lead(lead)

    @staticmethod
    async def qualify_lead(
        session: AsyncSession,
        lead_id: int,
        payload: Any,
        *,
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        async with command_transaction(session):
            return await LeadService._qualify_lead_mutation(
                session,
                lead_id,
                payload,
                tenant_scope=tenant_scope,
            )
