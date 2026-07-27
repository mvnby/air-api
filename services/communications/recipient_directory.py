from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from models import StaffUser
from services.communications.canary_errors import CommunicationsCanarySafetyError
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


class InstallationEstimateOwnerRecipientDirectory:
    """Resolve every active owner from StaffUser, or fail closed.

    This production audience deliberately has no manager or ``ADMIN_IDS``
    compatibility fallback. One malformed active owner invalidates the whole
    routing snapshot so a partial recipient set can never be materialized.
    """

    @classmethod
    async def list_telegram(
        cls,
        session: AsyncSession,
    ) -> list[CommunicationRecipientV1]:
        result = await session.execute(select(StaffUser).order_by(StaffUser.id.asc()))
        active_owners = [
            staff_user
            for staff_user in result.scalars().all()
            if staff_user.status == StaffUserService.STATUS_ACTIVE
            and staff_user.primary_role == StaffUserService.ROLE_OWNER
        ]
        if not active_owners:
            raise CommunicationsCanarySafetyError(
                "installation_owner_recipient_count_invalid"
            )

        recipients: list[CommunicationRecipientV1] = []
        recipient_keys: set[str] = set()
        destinations: set[str] = set()
        for staff_user in active_owners:
            if staff_user.id is None or staff_user.telegram_id is None:
                raise CommunicationsCanarySafetyError(
                    "installation_owner_recipient_invalid"
                )
            try:
                telegram_id = int(staff_user.telegram_id)
            except (TypeError, ValueError, OverflowError):
                raise CommunicationsCanarySafetyError(
                    "installation_owner_recipient_invalid"
                ) from None
            if telegram_id <= 0:
                raise CommunicationsCanarySafetyError(
                    "installation_owner_recipient_invalid"
                )
            recipient_key = f"staff:{int(staff_user.id)}"
            destination = str(telegram_id)
            if recipient_key in recipient_keys or destination in destinations:
                raise CommunicationsCanarySafetyError(
                    "installation_owner_recipient_duplicate"
                )
            recipient_keys.add(recipient_key)
            destinations.add(destination)
            recipients.append(
                CommunicationRecipientV1(
                    recipient_key=recipient_key,
                    destination=destination,
                    source="staff",
                    staff_user_id=int(staff_user.id),
                )
            )
        return recipients


class OperationsCanaryRecipientDirectory:
    """Resolve one immutable pair of active owner StaffUsers, or fail closed."""

    EXPECTED_RECIPIENT_COUNT = 2

    @classmethod
    async def list_telegram(
        cls,
        session: AsyncSession,
        *,
        required_recipient_keys: tuple[str, str] | None = None,
    ) -> list[CommunicationRecipientV1]:
        result = await session.execute(select(StaffUser).order_by(StaffUser.id.asc()))
        active_owners = [
            staff_user
            for staff_user in result.scalars().all()
            if StaffUserService.is_active(staff_user)
            and StaffUserService.primary_role(staff_user) == StaffUserService.ROLE_OWNER
        ]
        if len(active_owners) != cls.EXPECTED_RECIPIENT_COUNT:
            raise CommunicationsCanarySafetyError(
                "active_owner_recipient_count_invalid"
            )

        recipients: list[CommunicationRecipientV1] = []
        destinations: set[str] = set()
        for staff_user in active_owners:
            if staff_user.id is None or staff_user.telegram_id is None:
                raise CommunicationsCanarySafetyError(
                    "active_owner_recipient_invalid"
                )
            telegram_id = int(staff_user.telegram_id)
            if telegram_id <= 0:
                raise CommunicationsCanarySafetyError(
                    "active_owner_recipient_invalid"
                )
            destination = str(telegram_id)
            if destination in destinations:
                raise CommunicationsCanarySafetyError(
                    "active_owner_recipient_invalid"
                )
            destinations.add(destination)
            recipients.append(
                CommunicationRecipientV1(
                    recipient_key=f"staff:{int(staff_user.id)}",
                    destination=destination,
                    source="staff",
                    staff_user_id=int(staff_user.id),
                )
            )

        recipient_keys = tuple(recipient.recipient_key for recipient in recipients)
        if (
            required_recipient_keys is not None
            and recipient_keys != tuple(required_recipient_keys)
        ):
            raise CommunicationsCanarySafetyError(
                "active_owner_recipient_snapshot_changed"
            )
        return recipients
