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

    @classmethod
    async def list_images(cls, entity_type: str, slug: str) -> list[str]:
        """
        List all images for a given entity and slug.
        
        Args:
            entity_type: Type of entity
            slug: Slug of the entity
            
        Returns:
            List of web-accessible URLs
        """
        entity_dir = anyio.Path(cls.BASE_DIR) / entity_type / slug
        
        if not await entity_dir.exists():
            return []
            
        urls = []
        async for path in entity_dir.iterdir():
            if await path.is_file() and path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
                # Construct DB path then convert to web path
                # Ideally we store relative path in DB, but here we scan FS
                # path.relative_to(cls.BASE_DIR) might handle it but let's be careful with async path
                
                # Manual relative path construction for simplicity and safety
                relative_path = f"{cls.BASE_DIR}/{entity_type}/{slug}/{path.name}"
                urls.append(cls.get_web_path(relative_path))
                
        return sorted(urls)

    @classmethod
    async def download_and_save_image(
        cls,
        url: str,
        entity_type: str,
        slug: str
    ) -> str:
        """
        Download an image from a URL and save it to the filesystem.
        
        Args:
            url: Remote URL of the image
            entity_type: Type of entity
            slug: Slug of the entity
            
        Returns:
            Relative path for database storage (e.g., 'media/products/gree-09/uuid.jpg')
            Returns None if download fails.
        """
        import httpx
        
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, follow_redirects=True, timeout=10.0)
                if resp.status_code != 200:
                    print(f"Failed to download image: {url} (Status: {resp.status_code})")
                    return None
                    
                filename = url.split("/")[-1]
                # Clean filename of query params if any
                if "?" in filename:
                    filename = filename.split("?")[0]
                    
                return await cls.save_image(resp.content, entity_type, slug, filename)
        except Exception as e:
            print(f"Error downloading image {url}: {e}")
            return None


