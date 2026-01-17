"""
Service Layer: Analytics and Dashboard Statistics.
"""
from typing import Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, func
from sqlalchemy.orm import selectinload

from models import Product, Order, GlobalConfig

class AnalyticsService:
    """Service for dashboard analytics."""

    @staticmethod
    async def get_dashboard_stats(session: AsyncSession) -> Dict[str, Any]:
        """
        Get operational metrics for the Command Center Dashboard.
        """
        from datetime import datetime, timedelta, time
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        
        # 1. Financial Funnel (By Status)
        # Group by status, sum total_amount
        res = await session.execute(
            select(Order.status, func.count(Order.id), func.sum(Order.total_amount))
            .group_by(Order.status)
        )
        funnel_data = res.all()
        # Format: {"new_lead": {"count": 5, "sum": 50000}, ...}
        funnel_stats = {
            row[0]: {"count": row[1], "sum": float(row[2] or 0)} 
            for row in funnel_data
        }
        
        # 2. Action Items: Installations (Today & Tomorrow)
        # Filter: Status=INSTALLATION AND installation_date in [Today, Tomorrow]
        res = await session.execute(
            select(Order)
            .where(Order.status == "INSTALLATION")
            .where(Order.installation_date >= datetime.combine(today, time.min))
            .where(Order.installation_date <= datetime.combine(tomorrow, time.max))
            .options(selectinload(Order.customer))
            .order_by(Order.installation_date)
        )
        installs_soon = res.scalars().all()
        
        # 3. Action Items: Overdue Assessments
        # Filter: Status=ASSESSMENT AND assessment_date < Today
        res = await session.execute(
            select(Order)
            .where(Order.status == "ASSESSMENT")
            .where(Order.assessment_date < datetime.combine(today, time.min))
            .options(selectinload(Order.customer))
            .order_by(Order.assessment_date)
        )
        overdue_assessments = res.scalars().all()
        
        # 4. Installer Load
        # Active orders (not completed/canceled/new) assigned to installer
        # We need to join OrderInstaller -> Order
        from models import OrderInstaller, Installer, OrderStatus
        
        active_statuses = [
            OrderStatus.WON_DEPOSIT, 
            OrderStatus.INSTALLATION
        ]
        
        res = await session.execute(
            select(Installer.name, func.count(Order.id))
            .join(OrderInstaller, OrderInstaller.installer_id == Installer.id)
            .join(Order, Order.id == OrderInstaller.order_id)
            .where(Order.status.in_(active_statuses))
            .group_by(Installer.name)
        )
        installer_load = [{"name": row[0], "count": row[1]} for row in res.all()]

        # Basic Stats (Keep existing)
        res = await session.execute(select(func.count(Product.id)))
        total_products = res.scalar() or 0
        
        res = await session.execute(select(func.count(Order.id)))
        total_orders = res.scalar() or 0

        # Sync Mode
        res = await session.execute(
            select(GlobalConfig).where(GlobalConfig.key == "sync_mode")
        )
        sync_config = res.scalar_one_or_none()
        sync_mode = int(sync_config.value) if sync_config else 2

        return {
            "total_products": total_products,
            "total_orders": total_orders,
            "sync_mode": sync_mode,
            
            # New Operational Data
            "funnel": funnel_stats,
            "installations_soon": [
                {
                    "id": o.id,
                    "title": o.title or "Монтаж",
                    "customer": o.customer.name if o.customer else "—",
                    "date": o.installation_date.strftime("%d.%m %H:%M"),
                    "is_today": o.installation_date.date() == today
                } for o in installs_soon
            ],
            "overdue_assessments": [
                 {
                    "id": o.id,
                    "customer": o.customer.name if o.customer else "—",
                    "date": o.assessment_date.strftime("%d.%m %H:%M") if o.assessment_date else "—",
                    "phone": o.customer.phone if o.customer else ""
                } for o in overdue_assessments
            ],
            "installer_load": installer_load
        }
