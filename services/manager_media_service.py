"""Service-layer helpers for manager media/search workflows."""

import asyncio
from typing import List

from core.logger import logger
from duckduckgo_search import DDGS


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
