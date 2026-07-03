"""Shared-media ingestion helpers for importer pipelines."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import ImportMediaCache
from services.media_storage_service import ProductOriginalSourceStorage
from services.product_original_media_service import ProductOriginalMediaService

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
    async def _save_shared_file(
        content: bytes,
        *,
        source_storage: ProductOriginalSourceStorage | None = None,
    ) -> tuple[str, str]:
        async with _FILE_WRITE_LOCK:
            original = await ProductOriginalMediaService.save_shared_original(
                content,
                source_storage=source_storage,
            )
        return original.url, original.content_hash

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
        source_storage: ProductOriginalSourceStorage | None = None,
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
            parts = urlsplit(normalized_url)
            verify_tls = not parts.netloc.endswith("mdv-aircond.ru")
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=15.0,
                headers={"User-Agent": "Mozilla/5.0 (Codex Importer)"},
                verify=verify_tls,
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
            local_url, content_hash = await ImportMediaService._save_shared_file(
                response.content,
                source_storage=source_storage,
            )
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
