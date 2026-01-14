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
        Get aggregated statistics for the admin dashboard.
        
        Args:
            session: Active database session.
            
        Returns:
            Dictionary containing total products, orders, active products,
            sync mode, latest items, and latest orders.
        """
        # Total Products
        res = await session.execute(select(func.count(Product.id)))
        total_products = res.scalar() or 0
        
        # Active Products
        res = await session.execute(
            select(func.count(Product.id)).where(Product.is_published == True)
        )
        active_products = res.scalar() or 0
        
        # Total Orders
        res = await session.execute(select(func.count(Order.id)))
        total_orders = res.scalar() or 0
        
        # Sync Mode
        res = await session.execute(
            select(GlobalConfig).where(GlobalConfig.key == "sync_mode")
        )
        sync_config = res.scalar_one_or_none()
        sync_mode = int(sync_config.value) if sync_config else 2
        
        # Latest Imports (Products)
        res = await session.execute(
            select(Product).order_by(Product.created_at.desc()).limit(5)
        )
        latest_items = res.scalars().all()
        
        # Latest Orders
        res = await session.execute(
            select(Order)
            .options(selectinload(Order.customer))
            .order_by(Order.created_at.desc())
            .limit(5)
        )
        latest_orders = res.scalars().all()
        
        return {
            "total_products": total_products,
            "active_products": active_products,
            "total_orders": total_orders,
            "sync_mode": sync_mode,
            "latest_items": [
                {
                    "id": p.id, 
                    "title": p.title, 
                    "price": p.price, 
                    "created_at": p.created_at.strftime("%Y-%m-%d %H:%M")
                } 
                for p in latest_items
            ],
            "latest_orders": [
                {
                    "id": o.id, 
                    "customer": o.customer.name if o.customer else "N/A", 
                    "phone": o.customer.phone if o.customer else "N/A", 
                    "status": o.status,
                    "created_at": o.created_at.strftime("%Y-%m-%d %H:%M")
                } 
                for o in latest_orders
            ]
        }
