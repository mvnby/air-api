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
            product = Product(
                title=data['title'],
                description=data['description'],
                price=data['price'],
                area=data['area'],
                main_image=data['main_image'],
                images=data.get('images', []),
                categories=data.get('categories', []),
                specs=data.get('specs', {}),
                is_published=is_published
            )
            session.add(product)
            await session.commit()
            await session.refresh(product)
            return product
