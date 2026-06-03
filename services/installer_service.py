from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, or_, func

from models import Installer, StaffUser
from schemas import (
    ManagerInstallerCreatePayload,
    ManagerInstallerUpdatePayload,
    ManagerInstallerResponse,
    ManagerInstallerListResponse,
    Meta,
)
from services.staff_user_service import StaffUserService

class ManagerInstallerService:
    @staticmethod
    def _response_from_installer(inst: Installer, staff_user: StaffUser | None = None) -> ManagerInstallerResponse:
        status_active = (
            StaffUserService.is_active(staff_user)
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
    async def _staff_by_legacy_installer_id(cls, session: AsyncSession) -> dict[int, StaffUser]:
        result = await session.execute(select(StaffUser).where(StaffUser.legacy_installer_id.is_not(None)))
        users = list(result.scalars().all())
        return {int(user.legacy_installer_id): user for user in users if user.legacy_installer_id is not None}

    @classmethod
    async def get_all(
        cls,
        session: AsyncSession,
        page: int = 1,
        limit: int = 100,
        search: Optional[str] = None,
    ) -> ManagerInstallerListResponse:
        stmt = select(Installer)

        if search:
            search_query = f"%{search.lower()}%"
            staff_match = select(StaffUser.legacy_installer_id).where(
                StaffUser.legacy_installer_id.is_not(None),
                func.lower(StaffUser.display_name).like(search_query),
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

        staff_by_installer_id = await cls._staff_by_legacy_installer_id(session)
        items = []
        for inst in installers:
            items.append(cls._response_from_installer(inst, staff_by_installer_id.get(int(inst.id))))

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
    ) -> ManagerInstallerResponse:
        inst = Installer(
            name=payload.name,
            is_active=payload.is_active,
            default_rate=payload.default_rate,
            telegram_id=payload.telegram_id,
        )
        session.add(inst)
        await session.flush()
        await StaffUserService.ensure_for_installer(session, inst)
        await session.commit()
        await session.refresh(inst)
        staff_user = await StaffUserService.get_by_legacy_installer_id(session, int(inst.id))
        return cls._response_from_installer(inst, staff_user)

    @classmethod
    async def update(
        cls,
        session: AsyncSession,
        installer_id: int,
        payload: ManagerInstallerUpdatePayload,
    ) -> Optional[ManagerInstallerResponse]:
        res = await session.execute(select(Installer).where(Installer.id == installer_id))
        inst = res.scalar_one_or_none()
        if not inst:
            return None
            
        if payload.name is not None:
            inst.name = payload.name
        if payload.is_active is not None:
            inst.is_active = payload.is_active
        if payload.default_rate is not None:
            inst.default_rate = payload.default_rate
        if payload.telegram_id is not None:
            inst.telegram_id = payload.telegram_id

        session.add(inst)
        await session.flush()
        staff_user = await StaffUserService.ensure_for_installer(session, inst)
        if payload.is_active is not None:
            staff_user.status = StaffUserService.STATUS_ACTIVE if payload.is_active else StaffUserService.STATUS_INACTIVE
            session.add(staff_user)
        await session.commit()
        await session.refresh(inst)

        staff_user = await StaffUserService.get_by_legacy_installer_id(session, int(inst.id))
        return cls._response_from_installer(inst, staff_user)

    @classmethod
    async def search(
        cls,
        session: AsyncSession,
        q: str,
        limit: int = 50,
    ) -> ManagerInstallerListResponse:
        staff_users = await StaffUserService.find_active_executors_by_role(
            session,
            StaffUserService.ROLE_INSTALLER,
            search=q,
            limit=limit,
        )
        items = [
            cls._response_from_staff_user(user)
            for user in staff_users
            if user.legacy_installer_id is not None
        ]

        staff_by_installer_id = await cls._staff_by_legacy_installer_id(session)
        if len(items) < limit:
            stmt = select(Installer).where(Installer.is_active == True)

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
                if inst.id in staff_by_installer_id:
                    staff_user = staff_by_installer_id[inst.id]
                    if StaffUserService.can_be_executor(staff_user, StaffUserService.ROLE_INSTALLER):
                        items.append(cls._response_from_installer(inst, staff_user))
                        if len(items) >= limit:
                            break
                    continue
                items.append(cls._response_from_installer(inst))
                if len(items) >= limit:
                    break

        items.sort(key=lambda item: item.name.casefold())

        return ManagerInstallerListResponse(
            items=items,
            meta=Meta(total=len(items), page=1, limit=limit, pages=1),
        )
