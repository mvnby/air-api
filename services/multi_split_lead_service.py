"""Idempotent public lead capture with a structured configuration snapshot."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.multi_split import MultiSplitLeadPayload, MultiSplitLeadResponse
from models import LeadMultiSplitConfiguration
from models.tenancy import TenantScope
from schemas import LeadCreatePayload
from services.communications.tenant_website_event_service import TenantWebsiteEventService
from services.lead_service import LeadService
from services.multi_split_configuration_service import MultiSplitConfigurationService
from services.public_write_fingerprint_service import PublicWriteFingerprintService
from services.public_write_idempotency_service import PublicWriteCommandResponse, PublicWriteIdempotencyService


class MultiSplitLeadService:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        payload: MultiSplitLeadPayload,
        idempotency_key: str,
    ) -> MultiSplitLeadResponse:
        request_key_hash = PublicWriteIdempotencyService.key_hash(idempotency_key)

        async def create_once() -> PublicWriteCommandResponse[MultiSplitLeadResponse]:
            preview = await MultiSplitConfigurationService.preview(
                session, tenant_scope=tenant_scope, request=payload.configuration,
            )
            if preview.public.status == "incompatible":
                raise ValueError("Подтверждённый профиль исключает выбранный состав.")
            text = (
                f"Заявка на мультисплит: наружный #{payload.configuration.outdoor_product_id}; "
                f"помещений {len(payload.configuration.rooms)}; "
                f"статус {preview.public.status}; "
                f"оборудование {preview.public.equipment_total_byn} BYN"
            )
            if payload.message:
                text += f"\nКомментарий: {payload.message}"
            lead_data = await LeadService.create_lead(
                session,
                LeadCreatePayload(
                    source="site",
                    name=payload.name,
                    phone=payload.phone,
                    email=payload.email,
                    request_text=text,
                ),
                tenant_scope=tenant_scope,
            )
            lead_id = int(lead_data["id"])
            profile = preview.profile
            session.add(LeadMultiSplitConfiguration(
                lead_id=lead_id,
                rooms=[room.model_dump() for room in payload.configuration.rooms],
                component_snapshot=[item.model_dump() for item in preview.public.components],
                verification_status=preview.public.status,
                profile_id=int(profile.id) if profile is not None else None,
                profile_version=profile.version if profile is not None else None,
                source_url=profile.source_url if profile is not None else None,
                source_version=profile.source_version if profile is not None else None,
            ))
            await session.flush()
            await TenantWebsiteEventService.enqueue_contact_lead(
                session,
                lead_id=lead_id,
                status=str(lead_data["status"]),
                name=payload.name,
                phone=payload.phone,
                email=payload.email,
                address=None,
                message=text,
                tenant_scope=tenant_scope,
                request_key_hash=request_key_hash,
            )
            response = MultiSplitLeadResponse(lead_id=lead_id, status=str(lead_data["status"]))
            return PublicWriteCommandResponse(
                value=response, resource_type="lead", resource_id=lead_id,
            )

        outcome = await PublicWriteIdempotencyService.execute(
            session,
            tenant_scope=tenant_scope,
            command_name="public_multi_split_lead_v1",
            idempotency_key=idempotency_key,
            request_fingerprint=PublicWriteFingerprintService.for_payload(payload),
            response_model=MultiSplitLeadResponse,
            operation=create_once,
        )
        return outcome.value
