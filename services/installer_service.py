from typing import Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, or_, func

from models.order import Installer
from schemas import (
    ManagerInstallerCreatePayload,
    ManagerInstallerUpdatePayload,
    ManagerInstallerResponse,
    ManagerInstallerListResponse,
    Meta,
)

class ManagerInstallerService:

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
            stmt = stmt.where(func.lower(Installer.name).like(search_query))
            
        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_res = await session.execute(count_stmt)
        total = total_res.scalar() or 0
        
        # Paginate
        stmt = stmt.order_by(Installer.name.asc()).offset((page - 1) * limit).limit(limit)
        res = await session.execute(stmt)
        installers = res.scalars().all()
        
        items = []
        for inst in installers:
            items.append(ManagerInstallerResponse(
                id=inst.id,
                name=inst.name,
                is_active=inst.is_active,
                default_rate=inst.default_rate,
                telegram_id=inst.telegram_id,
            ))
            
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
        await session.commit()
        await session.refresh(inst)
        return ManagerInstallerResponse(
            id=inst.id,
            name=inst.name,
            is_active=inst.is_active,
            default_rate=inst.default_rate,
            telegram_id=inst.telegram_id,
        )

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
        await session.commit()
        await session.refresh(inst)
        
        return ManagerInstallerResponse(
            id=inst.id,
            name=inst.name,
            is_active=inst.is_active,
            default_rate=inst.default_rate,
            telegram_id=inst.telegram_id,
        )

    @classmethod
    async def search(
        cls,
        session: AsyncSession,
        q: str,
        limit: int = 50,
    ) -> ManagerInstallerListResponse:
        stmt = select(Installer).where(Installer.is_active == True)
        
        if q:
            search_query = f"%{q.lower()}%"
            stmt = stmt.where(func.lower(Installer.name).like(search_query))
            
        stmt = stmt.order_by(Installer.name.asc()).limit(limit)
        res = await session.execute(stmt)
        installers = res.scalars().all()
        
        items = []
        for inst in installers:
            items.append(ManagerInstallerResponse(
                id=inst.id,
                name=inst.name,
                is_active=inst.is_active,
                default_rate=inst.default_rate,
                telegram_id=inst.telegram_id,
            ))
            
        return ManagerInstallerListResponse(
            items=items,
            meta=Meta(total=len(items), page=1, limit=limit, pages=1),
        )
