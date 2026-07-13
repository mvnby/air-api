from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from models import StaffUser
from services.communications.contracts import CommunicationRecipientV1
from services.staff_user_service import StaffUserService


class ManagementRecipientDirectory:
    @staticmethod
    async def list_telegram(
        session: AsyncSession,
    ) -> list[CommunicationRecipientV1]:
        result = await session.execute(
            select(StaffUser)
            .where(StaffUser.telegram_id.is_not(None))
            .order_by(StaffUser.id.asc())
        )
        staff_users = list(result.scalars().all())

        recipients: list[CommunicationRecipientV1] = []
        seen_destinations: set[str] = set()
        # ADMIN_IDS is a compatibility bridge only. A legacy value must not
        # silently re-enable an inactive, blocked, or otherwise ineligible
        # database-backed StaffUser.
        database_destinations = {
            str(int(staff_user.telegram_id))
            for staff_user in staff_users
            if staff_user.telegram_id is not None
        }
        for staff_user in staff_users:
            if not StaffUserService.can_receive_admin_notifications(staff_user):
                continue
            if staff_user.id is None or staff_user.telegram_id is None:
                continue
            destination = str(int(staff_user.telegram_id))
            if destination in seen_destinations:
                continue
            seen_destinations.add(destination)
            recipients.append(
                CommunicationRecipientV1(
                    recipient_key=f"staff:{staff_user.id}",
                    destination=destination,
                    source="staff",
                    staff_user_id=int(staff_user.id),
                )
            )

        if recipients:
            return recipients

        for telegram_id in settings.admin_list:
            destination = str(int(telegram_id))
            if (
                destination in database_destinations
                or destination in seen_destinations
                or destination == "0"
            ):
                continue
            seen_destinations.add(destination)
            recipients.append(
                CommunicationRecipientV1(
                    recipient_key=f"legacy-telegram:{destination}",
                    destination=destination,
                    source="legacy",
                )
            )
        return recipients
