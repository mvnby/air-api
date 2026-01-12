"""
Service Layer: Product Business Logic.
This module contains search, filtering, and curation logic.
Uses ProductDAO for data access.
"""
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from thefuzz import process

from crud.product import ProductDAO
from models import Product


class ProductService:
    """
    Product business logic service.
    Methods accept session as first argument for DI/transaction control.
    """

    @staticmethod
    async def search(
        session: AsyncSession,
        query: Optional[str] = None,
        is_inverter: Optional[bool] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search products with fuzzy text matching.
        
        Args:
            session: Database session.
            query: Search text (fuzzy matched against title).
            is_inverter: Filter by inverter type.
            limit: Maximum results.
        
        Returns:
            List of product dictionaries (formatted for bot compatibility).
        """
        # Fetch all published products (filtered by inverter if specified)
        products = await ProductDAO.get_filtered(
            session,
            is_inverter=is_inverter,
            is_published=True
        )
        
        # Apply fuzzy search if query provided
        if query:
            choices = {p.id: p.title for p in products}
            matches = process.extract(query, choices, limit=limit)
            
            # Filter by match score >= 50%
            matched_ids = [m[2] for m in matches if m[1] >= 50]
            id_map = {p.id: p for p in products}
            products = [id_map[pid] for pid in matched_ids if pid in id_map]
        
        return [ProductService._to_dict(p) for p in products[:limit]]

    @staticmethod
    async def get_curated(
        session: AsyncSession,
        area: int,
        is_inverter: bool,
        limit: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Get curated product recommendations based on area and type.
        
        Args:
            session: Database session.
            area: Minimum area coverage needed.
            is_inverter: Whether to filter for inverter models.
            limit: Number of recommendations.
        
        Returns:
            List of product dictionaries (sorted by area, then price).
        """
        products = await ProductDAO.get_filtered(
            session,
            area_min=area,
            is_inverter=is_inverter,
            is_published=True,
            order_by_area=True,
            order_by_price=True,
            limit=limit
        )
        
        return [ProductService._to_dict(p) for p in products]

    @staticmethod
    async def get_by_id(session: AsyncSession, product_id: int) -> Optional[Dict[str, Any]]:
        """Get a single product by ID, formatted for bot."""
        product = await ProductDAO.get_by_id(session, product_id)
        if product:
            return ProductService._to_dict(product)
        return None

    @staticmethod
    async def get_all(session: AsyncSession) -> List[Dict[str, Any]]:
        """Get all published products, formatted for bot."""
        products = await ProductDAO.get_all_published(session)
        return [ProductService._to_dict(p) for p in products]

    @staticmethod
    async def get_by_area(
        session: AsyncSession,
        area: int,
        range_offset: int = 10
    ) -> List[Dict[str, Any]]:
        """Get products within an area range."""
        products = await ProductDAO.get_filtered(
            session,
            area_min=area,
            area_max=area + range_offset,
            is_published=True
        )
        return [ProductService._to_dict(p) for p in products]

    @staticmethod
    def _to_dict(product: Product) -> Dict[str, Any]:
        """
        Convert Product model to dictionary with bot-compatible format.
        Maintains backward compatibility with existing bot code.
        """
        data = product.model_dump()
        # Flatten tags to list of strings for bot compatibility
        data['categories'] = [t.title for t in product.tags]
        return data
