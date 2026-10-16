"""Resolve exactly one current staff Telegram recipient for a task event."""

from sqlalchemy.ext.asyncio import AsyncSession

from services.communications.contracts import CommunicationRecipientV1
from services.communications.staff_task_contracts import (
    StaffTaskNotificationPayloadV1,
)
from services.staff_user_service import StaffUserService
from services.staff_telegram_notifications import notification_identity


class StaffTaskRecipientDirectory:
    @staticmethod
    async def list_telegram(
        session: AsyncSession,
        *,
        payload: StaffTaskNotificationPayloadV1,
    ) -> list[CommunicationRecipientV1]:
        staff_user = await notification_identity(session, payload.staff_user_id)
        if (
            staff_user is None
            or not StaffUserService.is_active(staff_user)
            or staff_user.telegram_id is None
        ):
            return []
        from services.bot_notification_access import task_notification_allowed
        if not await task_notification_allowed(session, staff_user, payload):
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
