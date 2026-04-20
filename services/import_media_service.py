"""Shared-media ingestion helpers for importer pipelines."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from datetime import datetime
from io import BytesIO
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

import httpx
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import ImportMediaCache

logger = logging.getLogger(__name__)
_FILE_WRITE_LOCK = asyncio.Lock()


class ImportMediaService:
    @staticmethod
    def normalize_source_url(value: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        parts = urlsplit(raw)
        if not parts.scheme and not parts.netloc:
            return raw
        return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))

    @staticmethod
    async def _to_webp_bytes(content: bytes) -> bytes:
        def process(payload: bytes) -> bytes:
            img = Image.open(BytesIO(payload))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            output = BytesIO()
            img.save(output, format="WEBP", quality=85)
            return output.getvalue()

        return await asyncio.to_thread(process, content)

    @staticmethod
    async def _save_shared_file(content: bytes) -> tuple[str, str]:
        webp_content = await ImportMediaService._to_webp_bytes(content)
        content_hash = hashlib.sha256(webp_content).hexdigest()

        shared_dir = os.path.join("media", "products", "shared")
        os.makedirs(shared_dir, exist_ok=True)
        filename = f"{content_hash}.webp"
        file_path = os.path.join(shared_dir, filename)

        if not os.path.exists(file_path):
            async with _FILE_WRITE_LOCK:
                if not os.path.exists(file_path):
                    with open(file_path, "wb") as f:
                        f.write(webp_content)

        return f"/media/products/shared/{filename}", content_hash

    @staticmethod
    async def _upsert_cache_row(
        session: AsyncSession,
        *,
        source_url: str,
        local_url: str,
        content_hash: str,
    ) -> None:
        existing = (
            await session.execute(
                select(ImportMediaCache).where(ImportMediaCache.source_url == source_url)
            )
        ).scalar_one_or_none()
        now = datetime.now()
        if existing:
            existing.local_url = local_url
            existing.content_hash = content_hash
            existing.last_seen_at = now
            session.add(existing)
            return

        session.add(
            ImportMediaCache(
                source_url=source_url,
                local_url=local_url,
                content_hash=content_hash,
                created_at=now,
                last_seen_at=now,
            )
        )

    @staticmethod
    async def resolve_or_download(
        session: AsyncSession,
        *,
        source_url: str,
    ) -> Optional[str]:
        normalized_url = ImportMediaService.normalize_source_url(source_url)
        if not normalized_url:
            return None

        existing = (
            await session.execute(
                select(ImportMediaCache).where(ImportMediaCache.source_url == normalized_url)
            )
        ).scalar_one_or_none()
        if existing and existing.local_url:
            existing.last_seen_at = datetime.now()
            session.add(existing)
            return existing.local_url

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=15.0,
                headers={"User-Agent": "Mozilla/5.0 (Codex Importer)"},
            ) as client:
                response = await client.get(normalized_url)
        except Exception as exc:
            logger.warning("Import image download failed for %s: %s", normalized_url, exc)
            return None

        if response.status_code != 200:
            logger.warning(
                "Import image download failed for %s: status=%s",
                normalized_url,
                response.status_code,
            )
            return None

        try:
            local_url, content_hash = await ImportMediaService._save_shared_file(response.content)
        except Exception as exc:
            logger.warning("Import image processing failed for %s: %s", normalized_url, exc)
            return None

        resolved_url = ImportMediaService.normalize_source_url(str(response.url))
        await ImportMediaService._upsert_cache_row(
            session,
            source_url=normalized_url,
            local_url=local_url,
            content_hash=content_hash,
        )
        if resolved_url and resolved_url != normalized_url:
            await ImportMediaService._upsert_cache_row(
                session,
                source_url=resolved_url,
                local_url=local_url,
                content_hash=content_hash,
            )

        return local_url
