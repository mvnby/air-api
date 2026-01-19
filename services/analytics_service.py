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
        # Use simple string checks as DB returns strings now
        from models import OrderStatus
        
        res = await session.execute(
            select(Order)
            .where(Order.status == OrderStatus.INSTALLATION.value)
            .where(Order.installation_date >= datetime.combine(today, time.min))
            .where(Order.installation_date <= datetime.combine(tomorrow, time.max))
            .options(selectinload(Order.customer))
            .order_by(Order.installation_date)
        )
        installs_soon = res.scalars().all()
        
        # 3. Action Items: Overdue Assessments
        res = await session.execute(
            select(Order)
            .where(Order.status == OrderStatus.ASSESSMENT.value)
            .where(Order.assessment_date < datetime.combine(today, time.min))
            .options(selectinload(Order.customer))
            .order_by(Order.assessment_date)
        )
        overdue_assessments = res.scalars().all()
        
        # 4. Installer Load
        from models import OrderInstaller, Installer
        
        active_statuses = [
            OrderStatus.WON_DEPOSIT.value, 
            OrderStatus.INSTALLATION.value
        ]
        
        res = await session.execute(
            select(Installer.name, func.count(Order.id))
            .join(OrderInstaller, OrderInstaller.installer_id == Installer.id)
            .join(Order, Order.id == OrderInstaller.order_id)
            .where(Order.status.in_(active_statuses))
            .group_by(Installer.name)
        )
        installer_load = [{"name": row[0], "count": row[1]} for row in res.all()]

        # ... (Keep Basic Stats) ...
        # (Snippet shortened for brevity, skipping lines 78-95)
        res = await session.execute(select(func.count(Product.id)))
        total_products = res.scalar() or 0
        
        res = await session.execute(select(func.count(Order.id)))
        total_orders = res.scalar() or 0
        
        res = await session.execute(
            select(Product).order_by(Product.id.desc()).limit(5)
        )
        latest_products = res.scalars().all()

        res = await session.execute(
            select(Order).options(selectinload(Order.customer)).order_by(Order.id.desc()).limit(5)
        )
        latest_orders = res.scalars().all()

        # 7. Active Products Count
        res = await session.execute(select(func.count(Product.id)).where(Product.is_published == True))
        active_products = res.scalar() or 0

        # ... (Sync Mode) ...
        
        res = await session.execute(
            select(GlobalConfig).where(GlobalConfig.key == "sync_mode")
        )
        sync_config = res.scalar_one_or_none()
        sync_mode = int(sync_config.value) if sync_config else 2

        return {
            "total_products": total_products,
            "total_orders": total_orders,
            "active_products": active_products,
            "sync_mode": sync_mode,
            
            # Tables
            "latest_items": [
                {
                    "id": p.id,
                    "title": p.title,
                    "price": p.price
                } for p in latest_products
            ],
            "latest_orders": [
                {
                    "id": o.id,
                    "phone": o.customer.phone if o.customer else o.delivery_address or "-",
                    "status": o.status if isinstance(o.status, str) else o.status.value,
                    "amount": float(o.total_amount)
                } for o in latest_orders
            ],

            # New Operational Data
            "funnel": funnel_stats,
            "installations_soon": [
                {
                    "id": o.id,
                    "title": o.title or "Монтаж",
                    "customer": o.customer.name if o.customer else "—",
                    "date": o.installation_date.strftime("%d.%m %H:%M") if o.installation_date else "-",
                    "is_today": o.installation_date.date() == today if o.installation_date else False
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
