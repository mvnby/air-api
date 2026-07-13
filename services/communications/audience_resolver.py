from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from services.communications.contracts import (
    CommunicationRecipientV1,
    CommunicationTemplatePlanV1,
    TelegramCanaryRequestedPayloadV1,
)
from services.communications.recipient_directory import (
    ManagementRecipientDirectory,
    OperationsCanaryRecipientDirectory,
)
from services.communications.template_registry import UnsupportedCommunicationEvent


class CommunicationAudienceResolver:
    @staticmethod
    async def list_telegram(
        session: AsyncSession,
        *,
        plan: CommunicationTemplatePlanV1,
    ) -> list[CommunicationRecipientV1]:
        if plan.audience == "management":
            return await ManagementRecipientDirectory.list_telegram(session)
        if plan.audience == "operations_canary":
            payload = TelegramCanaryRequestedPayloadV1.model_validate(
                plan.render_context
            )
            return await OperationsCanaryRecipientDirectory.list_telegram(
                session,
                required_recipient_keys=payload.recipient_keys,
            )
        raise UnsupportedCommunicationEvent(
            f"Unsupported communication audience {plan.audience!r}"
        )
