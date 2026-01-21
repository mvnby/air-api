"""
Universal Image Service
Handles saving images to the filesystem with organized folder structure.
"""
import uuid
from pathlib import Path
import anyio


class ImageService:
    """Service for managing image uploads with entity-based folder structure."""
    
    BASE_DIR = Path("media")  # Base directory for all media files
    
    @classmethod
    async def save_image(
        cls,
        file_bytes: bytes,
        entity_type: str,
        slug: str,
        filename: str
    ) -> str:
        """
        Save an image to the filesystem with organized folder structure.
        
        Args:
            file_bytes: Raw bytes of the image file
            entity_type: Type of entity ('products', 'articles', etc.)
            slug: Slug of the entity (e.g., 'gree-09', 'how-to-choose')
            filename: Original filename (used only for extension extraction)
            
        Returns:
            Relative path for database storage (e.g., 'media/products/gree-09/uuid.jpg')
        """
        # Extract extension from original filename
        ext = filename.rsplit(".", 1)[-1] if "." in filename else "jpg"
        
        # Generate secure unique filename using uuid4
        unique_filename = f"{uuid.uuid4()}.{ext}"
        
        # Create directory structure: media/{entity_type}/{slug}/
        entity_dir = anyio.Path(cls.BASE_DIR) / entity_type / slug
        await entity_dir.mkdir(parents=True, exist_ok=True)
        
        # Full file path
        file_path = entity_dir / unique_filename
        
        # Write file asynchronously
        await file_path.write_bytes(file_bytes)
        
        # Return relative path for DB (using forward slashes for web compatibility)
        return str(file_path).replace("\\", "/")
    
    @classmethod
    def get_web_path(cls, db_path: str) -> str:
        """
        Convert database path to web-accessible path.
        
        Args:
            db_path: Path stored in database (e.g., 'media/products/gree-09/image.jpg')
            
        Returns:
            Web path with leading slash (e.g., '/media/products/gree-09/image.jpg')
        """
        if not db_path:
            return ""
        
        # Ensure path starts with /
        if not db_path.startswith("/"):
            return f"/{db_path}"
        
        return db_path
