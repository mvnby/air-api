from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import StaffUser, Storefront, TenantMembership
from services.communications.canary_errors import CommunicationsCanarySafetyError
from services.communications.contracts import CommunicationRecipientV1
from services.staff_user_service import StaffUserService
from services.staff_telegram_notifications import notifications_enabled


class ManagementRecipientDirectory:
    @staticmethod
    async def list_telegram(
        session: AsyncSession,
    ) -> list[CommunicationRecipientV1]:
        from services.tenant_scope_service import SystemTenantScopeResolver, TenantScopeResolutionError
        from models.tenancy import Tenant
        try:
            scope = await SystemTenantScopeResolver.resolve(session)
        except TenantScopeResolutionError:
            return []
        rows = (await session.execute(select(StaffUser, TenantMembership)
            .join(TenantMembership, TenantMembership.staff_user_id == StaffUser.id)
            .join(Tenant, Tenant.id == TenantMembership.tenant_id)
            .join(Storefront, Storefront.tenant_id == Tenant.id)
            .where(Tenant.id == scope.tenant_id, Tenant.status == 'active', Storefront.id == scope.storefront_id,
                   Storefront.status == 'active', TenantMembership.status == 'active',
                   TenantMembership.role.in_(['owner', 'admin', 'manager']), StaffUser.telegram_id.is_not(None))
            .order_by(StaffUser.id).execution_options(populate_existing=True))).all()
        recipients = []
        seen = set()
        for user, membership in rows:
            if not StaffUserService.is_active(user) or not notifications_enabled(user):
                continue
            destination = str(int(user.telegram_id))
            if destination in seen or destination == '0':
                continue
            seen.add(destination)
            recipients.append(CommunicationRecipientV1(recipient_key=f'staff:{user.id}', destination=destination,
                              source='staff', staff_user_id=int(user.id)))
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
            if not notifications_enabled(staff_user):
                continue
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


class TenantWebsiteManagementRecipientDirectory:
    """Resolve only active owner/admin memberships inside one tenant."""

    ELIGIBLE_MEMBERSHIP_ROLES = (
        StaffUserService.ROLE_OWNER,
        StaffUserService.ROLE_ADMIN,
    )

    @classmethod
    async def list_telegram(
        cls,
        session: AsyncSession,
        *,
        tenant_id: int,
        storefront_id: int,
    ) -> list[CommunicationRecipientV1]:
        normalized_tenant_id = int(tenant_id)
        normalized_storefront_id = int(storefront_id)
        from models.tenancy import Tenant
        storefront_exists = await session.scalar(
            select(Storefront.id).join(Tenant, Tenant.id == Storefront.tenant_id).where(
                Tenant.status == "active", Storefront.status == "active",
                Storefront.id == normalized_storefront_id,
                Storefront.tenant_id == normalized_tenant_id,
            )
        )
        if storefront_exists is None:
            raise CommunicationsCanarySafetyError(
                "tenant_website_scope_invalid"
            )

        rows = (
            await session.execute(
                select(TenantMembership, StaffUser)
                .join(
                    StaffUser,
                    StaffUser.id == TenantMembership.staff_user_id,
                )
                .where(
                    TenantMembership.tenant_id == normalized_tenant_id,
                    TenantMembership.status == "active",
                    TenantMembership.role.in_(
                        cls.ELIGIBLE_MEMBERSHIP_ROLES
                    ),
                    StaffUser.status == StaffUserService.STATUS_ACTIVE,
                )
                .order_by(StaffUser.id.asc()).execution_options(populate_existing=True)
            )
        ).all()

        recipients: list[CommunicationRecipientV1] = []
        recipient_keys: set[str] = set()
        destinations: set[str] = set()
        for membership, staff_user in rows:
            if not StaffUserService.is_active(staff_user) or not notifications_enabled(staff_user):
                continue
            if (
                membership.staff_user_id is None
                or staff_user.id is None
                or staff_user.telegram_id is None
            ):
                raise CommunicationsCanarySafetyError(
                    "tenant_website_recipient_invalid"
                )
            try:
                telegram_id = int(staff_user.telegram_id)
            except (TypeError, ValueError, OverflowError):
                raise CommunicationsCanarySafetyError(
                    "tenant_website_recipient_invalid"
                ) from None
            if telegram_id <= 0:
                raise CommunicationsCanarySafetyError(
                    "tenant_website_recipient_invalid"
                )
            recipient_key = f"staff:{int(staff_user.id)}"
            destination = str(telegram_id)
            if (
                recipient_key in recipient_keys
                or destination in destinations
            ):
                raise CommunicationsCanarySafetyError(
                    "tenant_website_recipient_duplicate"
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
            if not notifications_enabled(staff_user):
                continue
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
