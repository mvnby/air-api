"""Service-layer helpers for manager media/search workflows."""

import asyncio
import hashlib
import os
from io import BytesIO
from typing import List, Set

import httpx
from core.logger import logger
from duckduckgo_search import DDGS
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func
from sqlmodel import select, update

from models import Product, ProductImage


class ManagerMediaService:
    @staticmethod
    async def search_images(query: str, max_results: int = 20) -> List[dict]:
        """
        Search images in DuckDuckGo and return normalized lightweight payload.
        Returns empty list on provider errors/rate limits for graceful degradation.
        """
        try:
            results = await asyncio.to_thread(
                lambda: list(DDGS().images(query, max_results=max_results))
            )
        except Exception as exc:
            logger.error(f"Error searching images (DDG): {exc}")
            if "Ratelimit" in str(exc) or "403" in str(exc):
                logger.warning(f"DDG Ratelimit hit for query: {query}")
            return []

        images = []
        for result in results:
            if result.get("image"):
                images.append(
                    {
                        "image": result.get("image"),
                        "width": result.get("width"),
                        "height": result.get("height"),
                        "thumbnail": result.get("thumbnail"),
                    }
                )
        return images

    @staticmethod
    async def process_and_save_image(
        url: str,
        product_id: int,
        session: AsyncSession,
        *,
        set_main: bool,
        is_installation: bool = False,
    ) -> dict:
        """Download image by URL and persist it to gallery storage."""
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(url, timeout=10.0)
                response.raise_for_status()
                image_content = response.content
        except Exception as exc:
            logger.error(f"Failed to download image: {exc}")
            raise ValueError(f"Failed to download image: {exc}") from exc

        return await ManagerMediaService.save_image_from_bytes(
            image_content=image_content,
            product_id=product_id,
            session=session,
            set_main=set_main,
            is_installation=is_installation,
        )

    @staticmethod
    async def save_image_from_bytes(
        image_content: bytes,
        product_id: int,
        session: AsyncSession,
        *,
        set_main: bool,
        is_installation: bool = False,
    ) -> dict:
        """Process bytes, deduplicate storage by hash, and attach ProductImage link."""
        try:
            def process_image(content):
                img = Image.open(BytesIO(content))
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                output = BytesIO()
                img.save(output, format="WEBP", quality=85)
                return output.getvalue()

            webp_content = await asyncio.to_thread(process_image, image_content)
        except Exception as exc:
            logger.error(f"Failed to process image: {exc}")
            raise ValueError("Invalid image file") from exc

        content_hash = hashlib.sha256(webp_content).hexdigest()
        shared_dir = os.path.join("media", "products", "shared")
        os.makedirs(shared_dir, exist_ok=True)

        filename = f"{content_hash}.webp"
        file_path = os.path.join(shared_dir, filename)

        if not os.path.exists(file_path):
            try:
                async with asyncio.Lock():
                    with open(file_path, "wb") as file_obj:
                        file_obj.write(webp_content)
            except Exception as exc:
                logger.error(f"Failed to save file: {exc}")
                raise RuntimeError("Failed to save image file") from exc

        relative_url = f"/media/products/shared/{filename}"
        existing_stmt = select(ProductImage).where(
            ProductImage.product_id == product_id,
            ProductImage.url == relative_url,
        )
        existing_result = await session.execute(existing_stmt)
        existing_link = existing_result.scalar_one_or_none()

        if existing_link is None:
            new_image = ProductImage(
                product_id=product_id,
                url=relative_url,
                is_installation_photo=is_installation,
            )
            session.add(new_image)
        else:
            new_image = existing_link

        if set_main and not is_installation:
            statement = update(Product).where(Product.id == product_id).values(main_image=relative_url)
            await session.execute(statement)

        await ManagerMediaService.sync_legacy_images(session, product_id)
        await session.commit()
        await session.refresh(new_image)

        return {"url": relative_url, "id": new_image.id}

    @staticmethod
    async def sync_legacy_images(session: AsyncSession, product_id: int) -> None:
        """Sync ProductImage links to legacy Product.images JSON list."""
        product = await session.get(Product, product_id)
        if not product:
            return

        stmt = select(ProductImage).where(ProductImage.product_id == product_id)
        result = await session.execute(stmt)
        images = result.scalars().all()

        product.images = [img.url for img in images if not img.is_installation_photo]
        session.add(product)

    @staticmethod
    async def remove_file_if_unreferenced(session: AsyncSession, url: str) -> None:
        """Delete physical file only when no ProductImage/Product.main_image references remain."""
        gallery_ref_stmt = select(func.count()).select_from(ProductImage).where(ProductImage.url == url)
        gallery_refs = (await session.execute(gallery_ref_stmt)).scalar_one()

        main_ref_stmt = select(func.count()).select_from(Product).where(Product.main_image == url)
        main_refs = (await session.execute(main_ref_stmt)).scalar_one()

        if gallery_refs > 0 or main_refs > 0:
            return
        if not url.startswith("/media/"):
            return

        path = url.lstrip("/")
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception as exc:
                logger.error(f"Failed to delete unreferenced file {url}: {exc}")

    @staticmethod
    async def get_common_gallery_urls(
        session: AsyncSession,
        product_ids: List[int],
        *,
        exclude_installation: bool = True,
    ) -> Set[str]:
        """Get image URLs present in all selected products."""
        if not product_ids:
            return set()

        stmt = select(ProductImage).where(ProductImage.product_id.in_(product_ids))
        if exclude_installation:
            stmt = stmt.where(ProductImage.is_installation_photo == False)  # noqa: E712

        rows = (await session.execute(stmt)).scalars().all()
        by_url = {}
        target_ids = set(product_ids)
        for row in rows:
            by_url.setdefault(row.url, set()).add(row.product_id)
        return {url for url, linked in by_url.items() if linked == target_ids}
