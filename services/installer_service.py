from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, or_, func

from models import Installer, StaffUser, TenantMembership
from models.tenancy import TenantScope
from schemas import (
    ManagerInstallerCreatePayload,
    ManagerInstallerUpdatePayload,
    ManagerInstallerResponse,
    ManagerInstallerListResponse,
    Meta,
)
from services.staff_user_service import StaffUserService
from services.staff_tenant_membership_service import StaffTenantMembershipService

class ManagerInstallerService:
    @staticmethod
    def _response_from_installer(
        inst: Installer,
        staff_user: StaffUser | None = None,
        *,
        tenant_is_active: bool | None = None,
    ) -> ManagerInstallerResponse:
        status_active = (
            tenant_is_active
            if tenant_is_active is not None
            else StaffUserService.is_active(staff_user)
            if staff_user is not None
            else bool(inst.is_active)
        )
        return ManagerInstallerResponse(
            id=inst.id,
            name=staff_user.display_name if staff_user is not None else inst.name,
            is_active=status_active,
            default_rate=staff_user.default_rate if staff_user is not None else inst.default_rate,
            telegram_id=staff_user.telegram_id if staff_user is not None else inst.telegram_id,
        )

    @staticmethod
    def _response_from_staff_user(staff_user: StaffUser) -> ManagerInstallerResponse:
        return ManagerInstallerResponse(
            id=int(staff_user.legacy_installer_id or 0),
            name=staff_user.display_name,
            is_active=StaffUserService.is_active(staff_user),
            default_rate=staff_user.default_rate,
            telegram_id=staff_user.telegram_id,
        )

    @classmethod
    async def _staff_by_legacy_installer_id(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        active_membership_only: bool = False,
    ) -> dict[int, StaffUser]:
        stmt = (
            select(StaffUser)
            .join(
                TenantMembership,
                TenantMembership.staff_user_id == StaffUser.id,
            )
            .where(
                StaffUser.legacy_installer_id.is_not(None),
                TenantMembership.tenant_id == tenant_scope.tenant_id,
            )
        )
        if active_membership_only:
            stmt = stmt.where(TenantMembership.status == "active")
        result = await session.execute(stmt)
        users = list(result.scalars().all())
        return {int(user.legacy_installer_id): user for user in users if user.legacy_installer_id is not None}

    @staticmethod
    async def _active_tenant_installer_ids(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> set[int]:
        result = await session.execute(
            select(StaffUser.legacy_installer_id)
            .join(
                TenantMembership,
                TenantMembership.staff_user_id == StaffUser.id,
            )
            .where(
                StaffUser.legacy_installer_id.is_not(None),
                TenantMembership.tenant_id == tenant_scope.tenant_id,
                TenantMembership.status == "active",
            )
        )
        return {int(installer_id) for installer_id in result.scalars().all()}

    @staticmethod
    def _tenant_installer_clause(tenant_scope: TenantScope):
        tenant_installer_ids = (
            select(StaffUser.legacy_installer_id)
            .join(
                TenantMembership,
                TenantMembership.staff_user_id == StaffUser.id,
            )
            .where(
                StaffUser.legacy_installer_id.is_not(None),
                TenantMembership.tenant_id == tenant_scope.tenant_id,
            )
        )
        if not tenant_scope.is_system:
            return Installer.id.in_(tenant_installer_ids)

        all_linked_installer_ids = select(StaffUser.legacy_installer_id).where(
            StaffUser.legacy_installer_id.is_not(None)
        )
        return or_(
            Installer.id.in_(tenant_installer_ids),
            Installer.id.not_in(all_linked_installer_ids),
        )

    @classmethod
    async def get_all(
        cls,
        session: AsyncSession,
        page: int = 1,
        limit: int = 100,
        search: Optional[str] = None,
        *,
        tenant_scope: TenantScope,
    ) -> ManagerInstallerListResponse:
        stmt = select(Installer).where(cls._tenant_installer_clause(tenant_scope))

        if search:
            search_query = f"%{search.lower()}%"
            staff_match = select(StaffUser.legacy_installer_id).where(
                StaffUser.legacy_installer_id.is_not(None),
                func.lower(StaffUser.display_name).like(search_query),
                StaffUser.id.in_(
                    select(TenantMembership.staff_user_id).where(
                        TenantMembership.tenant_id == tenant_scope.tenant_id,
                    )
                ),
            )
            stmt = stmt.where(or_(func.lower(Installer.name).like(search_query), Installer.id.in_(staff_match)))

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_res = await session.execute(count_stmt)
        total = total_res.scalar() or 0
        
        # Paginate
        stmt = stmt.order_by(Installer.name.asc()).offset((page - 1) * limit).limit(limit)
        res = await session.execute(stmt)
        installers = res.scalars().all()

        staff_by_installer_id = await cls._staff_by_legacy_installer_id(
            session,
            tenant_scope=tenant_scope,
        )
        active_installer_ids = await cls._active_tenant_installer_ids(
            session,
            tenant_scope=tenant_scope,
        )
        items = []
        for inst in installers:
            staff_user = staff_by_installer_id.get(int(inst.id))
            items.append(
                cls._response_from_installer(
                    inst,
                    staff_user,
                    tenant_is_active=(int(inst.id) in active_installer_ids)
                    if staff_user is not None
                    else None,
                )
            )

        pages = (total + limit - 1) // limit if total > 0 else 1
        return ManagerInstallerListResponse(
            items=items,
            meta=Meta(total=total, page=page, limit=limit, pages=pages),
        )

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        payload: ManagerInstallerCreatePayload,
        *,
        tenant_scope: TenantScope,
    ) -> ManagerInstallerResponse:
        inst = Installer(
            name=payload.name,
            is_active=payload.is_active,
            default_rate=payload.default_rate,
            telegram_id=payload.telegram_id,
        )
        session.add(inst)
        await session.flush()
        await StaffUserService.ensure_for_installer(
            session,
            inst,
            tenant_scope=tenant_scope,
        )
        await session.commit()
        await session.refresh(inst)
        staff_user = await StaffUserService.get_by_legacy_installer_id(session, int(inst.id))
        return cls._response_from_installer(
            inst,
            staff_user,
            tenant_is_active=payload.is_active,
        )

    @classmethod
    async def update(
        cls,
        session: AsyncSession,
        installer_id: int,
        payload: ManagerInstallerUpdatePayload,
        *,
        tenant_scope: TenantScope,
    ) -> Optional[ManagerInstallerResponse]:
        res = await session.execute(select(Installer).where(Installer.id == installer_id))
        inst = res.scalar_one_or_none()
        if not inst:
            return None

        staff_user = await StaffUserService.get_by_legacy_installer_id(
            session,
            installer_id,
        )
        membership = None
        memberships = []
        if staff_user is not None:
            membership = await StaffTenantMembershipService.get_for_tenant(
                session,
                tenant_id=tenant_scope.tenant_id,
                staff_user_id=int(staff_user.id or 0),
            )
            if membership is None:
                return None
            memberships = await StaffTenantMembershipService.list_for_staff(
                session,
                staff_user_id=int(staff_user.id or 0),
                lock=True,
            )
            shared_fields: set[str] = set()
            if payload.name is not None:
                shared_fields.add("display_name")
            if payload.default_rate is not None:
                shared_fields.add("default_rate")
            if payload.telegram_id is not None:
                shared_fields.add("telegram_id")
            StaffTenantMembershipService.validate_shared_identity_update(
                changed_fields=shared_fields,
                membership_count=len(memberships),
                is_system_tenant=tenant_scope.is_system,
            )
        elif not tenant_scope.is_system:
            return None
            
        if payload.name is not None:
            inst.name = payload.name
        if payload.default_rate is not None:
            inst.default_rate = payload.default_rate
        if payload.telegram_id is not None:
            inst.telegram_id = payload.telegram_id

        session.add(inst)
        await session.flush()
        staff_user = await StaffUserService.ensure_for_installer(
            session,
            inst,
            tenant_scope=tenant_scope,
        )
        if payload.is_active is not None:
            membership = await StaffTenantMembershipService.get_for_tenant(
                session,
                tenant_id=tenant_scope.tenant_id,
                staff_user_id=int(staff_user.id or 0),
            )
            if membership is None:
                return None
            membership.status = "active" if payload.is_active else "disabled"
            StaffTenantMembershipService.touch(membership)
            session.add(membership)
            memberships = await StaffTenantMembershipService.list_for_staff(
                session,
                staff_user_id=int(staff_user.id or 0),
            )
            staff_user.status = StaffTenantMembershipService.aggregate_staff_status(
                memberships
            )
            inst.is_active = StaffUserService.is_active(staff_user)
            session.add(staff_user)
            session.add(inst)
        await session.commit()
        await session.refresh(inst)

        staff_user = await StaffUserService.get_by_legacy_installer_id(session, int(inst.id))
        membership = await StaffTenantMembershipService.get_for_tenant(
            session,
            tenant_id=tenant_scope.tenant_id,
            staff_user_id=int(staff_user.id or 0),
        )
        return cls._response_from_installer(
            inst,
            staff_user,
            tenant_is_active=bool(membership and membership.status == "active"),
        )

    @classmethod
    async def search(
        cls,
        session: AsyncSession,
        q: str,
        limit: int = 50,
        *,
        tenant_scope: TenantScope,
    ) -> ManagerInstallerListResponse:
        staff_users = await StaffUserService.find_active_executors_by_role(
            session,
            StaffUserService.ROLE_INSTALLER,
            search=q,
            limit=limit,
            tenant_scope=tenant_scope,
        )
        items = [
            cls._response_from_staff_user(user)
            for user in staff_users
            if user.legacy_installer_id is not None
        ]

        active_staff_by_installer_id = await cls._staff_by_legacy_installer_id(
            session,
            tenant_scope=tenant_scope,
            active_membership_only=True,
        )
        tenant_staff_by_installer_id = await cls._staff_by_legacy_installer_id(
            session,
            tenant_scope=tenant_scope,
        )
        if len(items) < limit:
            stmt = select(Installer).where(
                Installer.is_active == True,
                cls._tenant_installer_clause(tenant_scope),
            )

            if q:
                search_query = f"%{q.lower()}%"
                stmt = stmt.where(func.lower(Installer.name).like(search_query))

            stmt = stmt.order_by(Installer.name.asc()).limit(limit)
            res = await session.execute(stmt)
            installers = res.scalars().all()

            existing_response_ids = {item.id for item in items}
            for inst in installers:
                if inst.id in existing_response_ids:
                    continue
                if inst.id in active_staff_by_installer_id:
                    staff_user = active_staff_by_installer_id[inst.id]
                    if StaffUserService.can_be_executor(staff_user, StaffUserService.ROLE_INSTALLER):
                        items.append(cls._response_from_installer(inst, staff_user))
                        if len(items) >= limit:
                            break
                    continue
                if inst.id in tenant_staff_by_installer_id:
                    continue
                items.append(cls._response_from_installer(inst))
                if len(items) >= limit:
                    break

        items.sort(key=lambda item: item.name.casefold())

        return ManagerInstallerListResponse(
            items=items,
            meta=Meta(total=len(items), page=1, limit=limit, pages=1),
        )
