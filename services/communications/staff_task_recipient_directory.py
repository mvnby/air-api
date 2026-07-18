"""Resolve exactly one current staff Telegram recipient for a task event."""

from sqlalchemy.ext.asyncio import AsyncSession

from models import StaffUser
from services.communications.contracts import CommunicationRecipientV1
from services.communications.staff_task_contracts import (
    StaffTaskNotificationPayloadV1,
)
from services.staff_user_service import StaffUserService


class StaffTaskRecipientDirectory:
    @staticmethod
    async def list_telegram(
        session: AsyncSession,
        *,
        payload: StaffTaskNotificationPayloadV1,
    ) -> list[CommunicationRecipientV1]:
        staff_user = await session.get(StaffUser, payload.staff_user_id)
        if (
            staff_user is None
            or not StaffUserService.is_active(staff_user)
            or staff_user.telegram_id is None
            or staff_user.legacy_installer_id is None
        ):
            return []
        telegram_id = int(staff_user.telegram_id)
        if telegram_id == 0:
            return []
        return [
            CommunicationRecipientV1(
                recipient_key=f"staff:{payload.staff_user_id}",
                destination=str(telegram_id),
                source="staff",
                staff_user_id=payload.staff_user_id,
            )
        ]
