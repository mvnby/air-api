from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import TenantMembership


class StaffTenantMembershipService:
    """Keep tenant-local staff access separate from the shared identity."""

    SHARED_IDENTITY_FIELDS = frozenset(
        {
            "display_name",
            "username",
            "password",
            "phone",
            "email",
            "telegram_id",
            "telegram_username",
            "default_rate",
            "is_assignable_installer",
        }
    )

    @classmethod
    def validate_shared_identity_update(
        cls,
        *,
        changed_fields: set[str],
        membership_count: int,
        is_system_tenant: bool,
    ) -> None:
        if (
            membership_count > 1
            and not is_system_tenant
            and changed_fields.intersection(cls.SHARED_IDENTITY_FIELDS)
        ):
            raise ValueError(
                "Общие данные сотрудника с доступом к нескольким организациям "
                "может изменять только оператор платформы"
            )

    @staticmethod
    def membership_status(staff_status: str | None) -> str:
        normalized = str(staff_status or "").strip().lower()
        if normalized == "blocked":
            return "suspended"
        if normalized == "inactive":
            return "disabled"
        return "active"

    @staticmethod
    def staff_status(membership_status: str | None) -> str:
        normalized = str(membership_status or "").strip().lower()
        if normalized == "suspended":
            return "blocked"
        if normalized == "disabled":
            return "inactive"
        return "active"

    @classmethod
    def aggregate_staff_status(
        cls,
        memberships: list[TenantMembership],
    ) -> str:
        statuses = {
            str(membership.status or "").strip().lower()
            for membership in memberships
        }
        if "active" in statuses:
            return "active"
        if "suspended" in statuses:
            return "blocked"
        return "inactive"

    @staticmethod
    def touch(membership: TenantMembership) -> None:
        membership.updated_at = datetime.now(timezone.utc)

    @classmethod
    async def list_for_staff(
        cls,
        session: AsyncSession,
        *,
        staff_user_id: int,
        lock: bool = False,
    ) -> list[TenantMembership]:
        statement = (
            select(TenantMembership)
            .where(TenantMembership.staff_user_id == staff_user_id)
            .order_by(TenantMembership.id.asc())
        )
        if lock:
            statement = statement.with_for_update()
        return list((await session.execute(statement)).scalars().all())

    @classmethod
    async def ensure(
        cls,
        session: AsyncSession,
        *,
        tenant_id: int,
        staff_user_id: int,
        role: str,
        status: str,
    ) -> TenantMembership:
        membership = (
            await session.execute(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == tenant_id,
                    TenantMembership.staff_user_id == staff_user_id,
                )
            )
        ).scalars().first()
        if membership is not None:
            return membership
        membership = TenantMembership(
            tenant_id=tenant_id,
            staff_user_id=staff_user_id,
            role=role,
            status=status,
        )
        session.add(membership)
        await session.flush()
        return membership
