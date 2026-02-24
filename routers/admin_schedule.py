from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import selectinload
from sqlmodel import select

from core.database import async_session_maker
from core.security import get_current_username


router = APIRouter(tags=["admin-schedule"])


@router.get("/api/admin/installers/search")
async def search_installers(
    q: str = "",
    username: str = Depends(get_current_username)
):
    """
    Search installers for Select2.
    """
    from models import Installer

    async with async_session_maker() as session:
        stmt = select(Installer).where(Installer.is_active == True)
        if q:
            stmt = stmt.where(Installer.name.ilike(f"%{q}%"))

        result = await session.execute(stmt)
        installers = result.scalars().all()

        return [
            {
                "id": installer.id,
                "text": f"{installer.name} (TG: {installer.telegram_id or '-'})",
                "default_rate": installer.default_rate or 0
            }
            for installer in installers
        ]


@router.get("/calendar/events")
async def get_calendar_events(
    start: Optional[str] = None,
    end: Optional[str] = None,
    username: str = Depends(get_current_username)
):
    """
    Get events for FullCalendar (Orders with Installation or Assessment dates).
    """
    from models import Order, OrderStatus, OrderInstaller
    from sqlalchemy import or_

    async with async_session_maker() as session:
        stmt = select(Order).options(
            selectinload(Order.installers).selectinload(OrderInstaller.installer)
        ).where(
            or_(
                Order.installation_date.is_not(None),
                Order.measurement_date.is_not(None)
            )
        )

        if start:
            # Placeholder for future explicit date window filtering.
            pass

        result = await session.execute(stmt)
        orders = result.scalars().all()

        events = []
        for order in orders:
            if order.measurement_date:
                events.append({
                    "id": f"assess_{order.id}",
                    "title": f"🔍 Замер: {order.delivery_address or 'Без адреса'}",
                    "start": order.measurement_date.isoformat(),
                    "color": "#3b82f6",
                    "extendedProps": {"order_id": order.id}
                })

            if order.installation_date:
                color = "#22c55e"
                if order.status == OrderStatus.COMPLETED:
                    color = "#6b7280"
                elif order.status == OrderStatus.CANCELED:
                    color = "#ef4444"

                installers_str = ""
                if order.installers:
                    installers_str = " (" + ", ".join(
                        [installer.installer.name for installer in order.installers if installer.installer]
                    ) + ")"

                events.append({
                    "id": f"install_{order.id}",
                    "title": f"🛠️ Монтаж: {order.delivery_address or 'Без адреса'}{installers_str}",
                    "start": order.installation_date.isoformat(),
                    "color": color,
                    "extendedProps": {"order_id": order.id}
                })

        return events
