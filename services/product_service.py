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

# Транслитерация RU → EN для поиска
TRANSLIT_MAP = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
    'ы': 'y', 'э': 'e', 'ю': 'yu', 'я': 'ya', 'ь': '', 'ъ': ''
}

def transliterate(text: str) -> str:
    """Транслитерирует русский текст в латиницу."""
    result = []
    for char in text.lower():
        result.append(TRANSLIT_MAP.get(char, char))
    return ''.join(result)


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
        Search products with fuzzy text matching and transliteration support.
        
        Args:
            session: Database session.
            query: Search text (fuzzy matched against title, supports RU→EN transliteration).
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
            # Case-insensitive: lowercase все для сравнения
            query_lower = query.lower()
            choices = {p.id: p.title.lower() for p in products}
            
            # Пробуем оригинальный запрос
            matches = process.extract(query_lower, choices, limit=limit)
            matched_ids = [m[2] for m in matches if m[1] >= 60]  # Порог 60%
            
            # Если мало результатов — пробуем транслитерацию
            if len(matched_ids) < 2:
                translit_query = transliterate(query)
                if translit_query != query_lower:
                    translit_matches = process.extract(translit_query, choices, limit=limit)
                    for m in translit_matches:
                        if m[1] >= 60 and m[2] not in matched_ids:
                            matched_ids.append(m[2])
            
            id_map = {p.id: p for p in products}
            products = [id_map[pid] for pid in matched_ids if pid in id_map]
        
        return [ProductService._to_dict(p) for p in products[:limit]]

    @staticmethod
    async def get_curated(
        session: AsyncSession,
        area: int,
        is_inverter: bool,
        tag_slugs: Optional[List[str]] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get curated product recommendations based on area, type, and optional tags.
        
        Args:
            session: Database session.
            area: Minimum area coverage needed.
            is_inverter: Whether to filter for inverter models.
            tag_slugs: Optional list of tag slugs to filter by (e.g., ['winter-20', 'wifi-builtin']).
            limit: Number of recommendations (default 5).
        
        Returns:
            List of product dictionaries (sorted by area, then price).
        """
        # Resolve tag slugs to grouped IDs for faceted filtering
        faceted_tag_ids = None
        if tag_slugs:
            faceted_tag_ids = await ProductService.resolve_slugs_to_grouped_ids(session, tag_slugs)
        
        products = await ProductDAO.get_filtered(
            session,
            area_min=area,
            is_inverter=is_inverter,
            is_published=True,
            faceted_tag_ids=faceted_tag_ids,
            sort="area_asc",  # Сортировка по площади, затем по цене
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
    async def get_product_by_identifier(session: AsyncSession, identifier: str) -> Optional[Product]:
        """Fetch a single product by ID (if numeric) or slug (Hybrid Access)."""
        if identifier.isdigit():
            product = await ProductDAO.get_by_id(session, int(identifier))
            if product:
                return product
        return await ProductDAO.get_by_slug(session, identifier)

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
    async def resolve_slugs_to_grouped_ids(
        session: AsyncSession,
        slugs: List[str]
    ) -> Dict[int, List[int]]:
        """
        Resolves a list of tag slugs to their IDs, grouped by TagGroup ID.
        Returns: {group_id: [tag_id1, tag_id2]}
        """
        from models import Tag
        from sqlmodel import select
        
        if not slugs:
            return {}
            
        stmt = select(Tag).where(Tag.slug.in_(slugs))
        result = await session.execute(stmt)
        tags = result.scalars().all()
        
        grouped: Dict[int, List[int]] = {}
        
        for tag in tags:
            # If tag has no group, we put it in a "None" group (key 0 or None)
            # But query logic needs to handle it. 
            # If no group, treating as separate "tags" is tricky in faceted search.
            # Let's assume all faceted tags belong to a group. 
            # If not, we can put them in a special bucket or just ignore group logic.
            # For this implementation, we map None group to 0.
            g_id = tag.group_id if tag.group_id else 0
            
            if g_id not in grouped:
                grouped[g_id] = []
            grouped[g_id].append(tag.id)
            
        return grouped

    @staticmethod
    def _to_dict(product: Product) -> Dict[str, Any]:
        """
        Convert Product model to dictionary with bot-compatible format.
        Maintains backward compatibility with existing bot code.
        """
        data = product.model_dump()
        # Flatten tags to list of strings for bot compatibility
        data['categories'] = [t.title for t in product.tags]
        
        # Serialize full tags with groups for Frontend
        tags_data = []
        for tag in product.tags:
            t_dict = tag.model_dump()
            if tag.group:
                t_dict['group'] = tag.group.model_dump()
            tags_data.append(t_dict)
        data['tags'] = tags_data

        # --- GALLERY FIX & SYNC (Phase 47/48) ---
        # The Manager App writes to 'gallery_images' (Relation), 
        # but Frontend/Admin read 'images' (Legacy JSON).
        # We bridge this gap here by populating 'images' from the relation.
        
        # 1. Get images from relation and sort them
        # Sort priority: 
        #   - Product photos first (is_installation_photo=False)
        #   - Then by ID (creation order)
        gallery = sorted(
            product.gallery_images, 
            key=lambda x: (x.is_installation_photo, x.id)
        )

        # 2. Populate Legacy JSON field (URLs only) for Frontend/Admin compatibility
        # Filter out installation photos if we only want product shots in the main gallery
        # (Though usually customers want to see everything). 
        # Let's include everything for now, or maybe only is_installation_photo=False?
        # User request implies "Gallery" which usually means product photos.
        # But let's verify if 'images' should contain installation photos.
        # Frontend distinguishes them? No, frontend just loops.
        # We will include ALL, but sorted (Installation last).
        data['images'] = [img.url for img in gallery]

        # 3. Populate New Field (Full Objects) for advanced UI
        data['gallery_images'] = [img.model_dump() for img in gallery]
        
        return data

    @staticmethod
    async def save_main_image(
        session: AsyncSession,
        product_id: int,
        file_bytes: bytes,
        filename: str
    ) -> Optional[str]:
        """
        Save main image for a product.
        
        Args:
            session: Database session
            product_id: ID of the product
            file_bytes: Raw bytes of the image file
            filename: Original filename
            
        Returns:
            Web path to the saved image (with leading slash) or None if product not found
        """
        from services.image_service import ImageService
        from sqlmodel import select
        
        # Fetch product
        stmt = select(Product).where(Product.id == product_id)
        result = await session.execute(stmt)
        product = result.scalar_one_or_none()
        
        if not product:
            return None
        
        # Save image using ImageService
        db_path = await ImageService.save_image(
            file_bytes=file_bytes,
            entity_type="products",
            slug=product.slug,
            filename=filename
        )
        
        # Get web path with leading slash
        web_path = ImageService.get_web_path(db_path)
        
        # Update product
        product.main_image = web_path
        session.add(product)
        await session.commit()
        await session.refresh(product)
        
        return web_path

    @staticmethod
    async def add_gallery_images(
        session: AsyncSession,
        product_id: int,
        images_data: List[Dict[str, Any]]
    ) -> List[int]:
        """
        Add multiple gallery images to a product.
        
        Args:
            session: Database session
            product_id: ID of the product
            images_data: List of dicts with keys: file_bytes, filename, is_installation_photo
            
        Returns:
            List of created ProductImage IDs
        """
        from services.image_service import ImageService
        from models import ProductImage
        from sqlmodel import select
        
        # Fetch product
        stmt = select(Product).where(Product.id == product_id)
        result = await session.execute(stmt)
        product = result.scalar_one_or_none()
        
        if not product:
            return []
        
        created_ids = []
        for img_data in images_data:
            # Save image file
            db_path = await ImageService.save_image(
                file_bytes=img_data["file_bytes"],
                entity_type="products",
                slug=product.slug,
                filename=img_data["filename"]
            )
            
            # Create ProductImage record
            web_path = ImageService.get_web_path(db_path)
            product_image = ProductImage(
                product_id=product_id,
                url=web_path,
                is_installation_photo=img_data.get("is_installation_photo", False)
            )
            session.add(product_image)
            await session.flush()
            created_ids.append(product_image.id)
        
        await session.commit()
        return created_ids

    @staticmethod
    async def bulk_update_tags(
        session: AsyncSession,
        product_ids: List[int],
        tag_ids: List[int],
        action: str
    ) -> int:
        """
        Bulk add or remove tags from multiple products.
        
        Args:
            session: Database session
            product_ids: List of product IDs to update
            tag_ids: List of tag IDs to add/remove
            action: Either "add" or "remove"
            
        Returns:
            Number of products updated
        """
        from sqlmodel import select
        from sqlalchemy.orm import selectinload
        from models import Tag
        
        # Fetch products with tags loaded
        stmt = select(Product).where(Product.id.in_(product_ids)).options(
            selectinload(Product.tags)
        )
        result = await session.execute(stmt)
        products = result.scalars().all()
        
        # Fetch tags to apply
        tag_stmt = select(Tag).where(Tag.id.in_(tag_ids))
        tag_result = await session.execute(tag_stmt)
        tags_to_apply = tag_result.scalars().all()
        
        # Apply changes
        for product in products:
            if action == "add":
                current_tag_ids = {t.id for t in product.tags}
                for tag in tags_to_apply:
                    if tag.id not in current_tag_ids:
                        product.tags.append(tag)
            elif action == "remove":
                product.tags = [t for t in product.tags if t.id not in tag_ids]
        
        await session.commit()
        return len(products)
