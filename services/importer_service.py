from typing import List, Optional
from parsers.base import BaseParser
from parsers.onliner import OnlinerParser
from database import async_session_maker
from models import Product

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

    async def import_product(self, url: str) -> Product:
        """
        Orchestrates the import process: find parser -> parse -> save to DB.
        """
        url = url.strip().replace('\r', '').replace('\n', '')
        async with async_session_maker() as session:
            # 0. Check for duplicates (live products only)
            from sqlmodel import select
            stmt = select(Product).where(Product.source_url == url)
            result = await session.execute(stmt)
            if result.scalar_one_or_none():
                raise ValueError(f"Product with URL '{url}' already exists in the database.")

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
            auto_slugs = get_auto_tags(metrics)
            
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

            product = Product(
                title=data['title'],
                description=data['description'],
                price=data['price'],
                area=data['area'],
                main_image=data['main_image'],
                images=data.get('images', []),
                tags=tag_objects,
                specs=data.get('specs', {}),
                is_published=is_published,
                source_url=url
            )
            session.add(product)
            await session.commit()
            await session.refresh(product)
            return product

    async def import_products_bulk(self, urls: List[str]) -> dict:
        """
        Imports multiple products and returns a summary of success/errors.
        """
        results = {"success": [], "errors": []}
        for url in urls:
            # Thorough cleaning of URLs
            url = url.strip().replace('\r', '').replace('\n', '')
            if not url: continue
            try:
                product = await self.import_product(url)
                results["success"].append(f"'{product.title}' (ID: {product.id})")
            except Exception as e:
                results["errors"].append(f"URL '{url}': {str(e)}")
        return results
