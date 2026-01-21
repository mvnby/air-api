"""
Service Layer: Article Business Logic.
Handles article operations including cover image management.
"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Article
from services.image_service import ImageService


class ArticleService:
    """
    Article business logic service.
    Methods accept session as first argument for DI/transaction control.
    """

    @staticmethod
    async def save_cover_image(
        session: AsyncSession,
        article_id: int,
        file_bytes: bytes,
        filename: str
    ) -> Optional[str]:
        """
        Save cover image for an article.
        
        Args:
            session: Database session
            article_id: ID of the article
            file_bytes: Raw bytes of the image file
            filename: Original filename
            
        Returns:
            Web path to the saved image (with leading slash) or None if article not found
        """
        # Fetch article
        stmt = select(Article).where(Article.id == article_id)
        result = await session.execute(stmt)
        article = result.scalar_one_or_none()
        
        if not article:
            return None
        
        # Save image using ImageService
        db_path = await ImageService.save_image(
            file_bytes=file_bytes,
            entity_type="articles",
            slug=article.slug,
            filename=filename
        )
        
        # Get web path with leading slash
        web_path = ImageService.get_web_path(db_path)
        
        # Update article
        article.cover_image = web_path
        session.add(article)
        await session.commit()
        await session.refresh(article)
        
        return web_path
