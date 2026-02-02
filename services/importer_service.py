from typing import List, Optional
from parsers.base import BaseParser
from parsers.onliner import OnlinerParser
from core.database import async_session_maker
from models import Product
from services.image_service import ImageService

class ImporterService:
    def __init__(self):
        # Register available parsers
        self.parsers: List[BaseParser] = [
            OnlinerParser()
        ]

    def get_parser(self, url: str) -> Optional[BaseParser]:
        """Finds a parser that supports the given URL."""
        for parser in self.parsers:
            if parser.supports(url):
                return parser
        return None

    async def import_product(self, url: str) -> dict:
        """
        Orchestrates the import process: find parser -> parse -> save to DB.
        Returns a dict: {'product': Product, 'related_urls': List[str]}
        """
        url = url.strip().replace('\r', '').replace('\n', '')
        async with async_session_maker() as session:
            # 0. Check for duplicates (live products only)
            from sqlmodel import select
            stmt = select(Product).where(Product.source_url == url)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                # We return it but maybe don't re-save. 
                # For the sake of bulk import, we'll return the existing one.
                return {"product": existing, "related_urls": []}

            parser = self.get_parser(url)
            if not parser:
                raise ValueError("No parser found for this URL")

            data = await parser.parse(url)
            
            # Determine publishing status
            is_published = True 

            # Resolve Categories/Tags
            tag_names = data.get('categories', [])
            tag_objects = []
            
            from models import Tag
            from sqlmodel import or_
            import slugify
            from services.tag_logic import get_auto_tags
            
            # 1. Get Auto Tags (Slugs) based on metrics
            metrics = data.get('metrics', {})
            auto_slugs = get_auto_tags(metrics, specs=data.get('specs', {}))
            
            # 2. Resolve Auto Tags by SLUG
            for slug in auto_slugs:
                stmt = select(Tag).where(Tag.slug == slug)
                result = await session.execute(stmt)
                tag = result.scalar_one_or_none()
                if tag:
                    tag_objects.append(tag)
            
            # 3. Resolve old string categories (Title based)
            for t_name in tag_names:
                t_name = t_name.strip()
                if not t_name: continue
                
                stmt = select(Tag).where(Tag.title == t_name)
                result = await session.execute(stmt)
                tag = result.scalar_one_or_none()
                
                if not tag:
                    slug = slugify.slugify(t_name)
                    tag = Tag(title=t_name, slug=slug, is_public=True)
                    session.add(tag)
                
                if tag not in tag_objects:
                    tag_objects.append(tag)

            # 4. Handle Images (Download to local storage)
            slug = data.get('slug')
            # Fallback if slug missing (shouldn't happen with updated OnlinerParser)
            if not slug:
                slug = slugify.slugify(data['title'])

            # Main Image
            main_image_url = data.get('main_image')
            local_main_image = None
            if main_image_url:
                local_main_image = await ImageService.download_and_save_image(
                    main_image_url, 'products', slug
                )
            
            # --- STOP LEGACY GALLERY PARSING (Phase 48) ---
            # We no longer download 'images' array from Onliner/Source.
            # Only 'main_image' is kept.
            # Gallery is filled manually via Manager App.
            local_gallery_images = []

            product = Product(
                title=data['title'],
                slug=slug,
                description=data['description'],
                price=data['price'],
                area=data['area'],
                is_inverter=metrics.get('is_inverter', False),
                power_cooling=metrics.get('power_cooling'),
                main_image=local_main_image,  # Use local path
                images=[],  # Explicitly empty legacy JSON
                tags=tag_objects,
                specs=data.get('specs', {}),
                is_published=is_published,
                source_url=url
            )
            session.add(product)
            await session.commit()
            await session.refresh(product)
            return {"product": product, "related_urls": data.get('related_urls', [])}

    async def import_products_bulk(self, urls: List[str], with_related: bool = False) -> dict:
        """
        Imports multiple products and returns a summary of success/errors.
        Can recursively import related products.
        """
        results = {"success": [], "errors": []}
        processed_urls = set()
        pending_urls = [u.strip().replace('\r', '').replace('\n', '') for u in urls if u.strip()]

        while pending_urls:
            url = pending_urls.pop(0)
            if url in processed_urls: continue
            
            try:
                res = await self.import_product(url)
                product = res["product"]
                # Only add to 'success' if it's a NEW import (or just count it)
                # To keep it simple, we count all as success if they are in DB now.
                results["success"].append(f"'{product.title}' (ID: {product.id})")
                
                processed_urls.add(url)
                
                if with_related:
                    for rel_url in res["related_urls"]:
                        if rel_url not in processed_urls and rel_url not in pending_urls:
                            pending_urls.append(rel_url)
            except Exception as e:
                results["errors"].append(f"URL '{url}': {str(e)}")
                processed_urls.add(url)

        return results
