from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import Installer, Order, OrderInstaller, OrderStatus


class AdminScheduleService:
    @staticmethod
    async def search_installers(session: AsyncSession, q: str = "") -> List[Dict[str, Any]]:
        stmt = select(Installer).where(Installer.is_active == True)
        if q:
            stmt = stmt.where(Installer.name.ilike(f"%{q}%"))

        result = await session.execute(stmt)
        installers = result.scalars().all()

        return [
            {
                "id": installer.id,
                "text": f"{installer.name} (TG: {installer.telegram_id or '-'})",
                "default_rate": installer.default_rate or 0,
            }
            for installer in installers
        ]

    @staticmethod
    async def get_calendar_events(
        session: AsyncSession,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        # `start`/`end` are accepted for FullCalendar compatibility; legacy
        # behavior returned all dated orders, so filtering stays unchanged.
        stmt = (
            select(Order)
            .options(selectinload(Order.installers).selectinload(OrderInstaller.installer))
            .where(
                or_(
                    Order.installation_date.is_not(None),
                    Order.measurement_date.is_not(None),
                )
            )
        )

        result = await session.execute(stmt)
        orders = result.scalars().all()

        events = []
        for order in orders:
            if order.measurement_date:
                events.append(
                    {
                        "id": f"assess_{order.id}",
                        "title": f"🔍 Замер: {order.delivery_address or 'Без адреса'}",
                        "start": order.measurement_date.isoformat(),
                        "color": "#3b82f6",
                        "extendedProps": {"order_id": order.id},
                    }
                )

            if order.installation_date:
                color = "#22c55e"
                if order.status == OrderStatus.CLOSED:
                    if order.closing_result == "won":
                        color = "#6b7280"
                    elif order.closing_result == "lost":
                        color = "#ef4444"

                installers_str = ""
                if order.installers:
                    installers_str = " (" + ", ".join(
                        [installer.installer.name for installer in order.installers if installer.installer]
                    ) + ")"

                events.append(
                    {
                        "id": f"install_{order.id}",
                        "title": f"🛠️ Монтаж: {order.delivery_address or 'Без адреса'}{installers_str}",
                        "start": order.installation_date.isoformat(),
                        "color": color,
                        "extendedProps": {"order_id": order.id},
                    }
                )

        return events
