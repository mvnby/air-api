from datetime import datetime, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.order import Order
from models.customer import Customer
from models.common import OrderStatus
from schemas import DashboardStatsResponse, DashboardTouchpoint

class StatsService:
    @staticmethod
    async def get_dashboard_stats(session: AsyncSession) -> DashboardStatsResponse:
        now = datetime.now()
        start_of_month = datetime(now.year, now.month, 1)

        # 1. Total Amount for CLOSED deals in the current month
        total_stmt = select(func.sum(Order.total_amount)).where(
            Order.status == OrderStatus.CLOSED,
            Order.created_at >= start_of_month
        )
        total_result = await session.execute(total_stmt)
        total_amount = total_result.scalar() or 0.0

        # 2. New Leads count in the current month
        leads_stmt = select(func.count(Order.id)).where(
            Order.status == OrderStatus.NEW_LEAD,
            Order.created_at >= start_of_month
        )
        leads_result = await session.execute(leads_stmt)
        new_leads_count = leads_result.scalar() or 0

        # 3. Upcoming Touchpoints
        # Find orders with next_followup_date <= 7 days from now, not in closed statuses
        end_of_window = now + timedelta(days=7)
        
        touchpoints_stmt = (
            select(Order)
            .options(selectinload(Order.customer))
            .where(
                Order.next_followup_date.is_not(None),
                Order.next_followup_date <= end_of_window,
                Order.status != OrderStatus.CLOSED
            )
            .order_by(Order.next_followup_date.asc())
            .limit(5)
        )
        touchpoints_result = await session.execute(touchpoints_stmt)
        orders = touchpoints_result.scalars().all()

        touchpoints = []
        for order in orders:
            customer_name = order.customer.name if order.customer else "Неизвестный клиент"
            phone = order.customer.phone if order.customer else None
            
            touchpoints.append(
                DashboardTouchpoint(
                    order_id=order.id,
                    customer_name=customer_name,
                    phone=phone,
                    next_followup_date=order.next_followup_date,
                    title=order.title
                )
            )

        return DashboardStatsResponse(
            total_amount=float(total_amount),
            new_leads_count=new_leads_count,
            upcoming_touchpoints=touchpoints
        )
