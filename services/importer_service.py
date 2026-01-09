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
        parser = self.get_parser(url)
        if not parser:
            raise ValueError("No parser found for this URL")

        data = await parser.parse(url)
        
        # Determine publishing status
        is_published = True 

        async with async_session_maker() as session:
            # Resolve Categories/Tags
            tag_names = data.get('categories', [])
            tag_objects = []
            
            from models import Tag
            from sqlmodel import select, or_
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
            # This is for backward compatibility or extra tags from parser
            for t_name in tag_names:
                t_name = t_name.strip()
                if not t_name: continue
                
                # Try to map common names to slugs or find by title
                # Only add if not already added
                
                # Check if exists by Title
                stmt = select(Tag).where(Tag.title == t_name)
                result = await session.execute(stmt)
                tag = result.scalar_one_or_none()
                
                if not tag:
                    # Optional: Don't create new tags automatically if we want strict control?
                    # User didn't specify. For now, let's keep creating but maybe mark as unverified?
                    # Or just create.
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
                tags=tag_objects, # Pass objects here
                specs=data.get('specs', {}),
                is_published=is_published
            )
            session.add(product)
            await session.commit()
            await session.refresh(product)
            return product
