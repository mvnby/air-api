"""Synchronize one bounded page of public market publications."""

import asyncio
import logging
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import async_session_maker
from crud.tender_market import TenderMarketDAO
from models import TenderMarketPublication
from schemas_tender_market import MarketPageInput, MarketPublicationInput
from services.belzakupki_canonical_identity import canonical_procurement_url
from services.tender_lot_snapshot import native_lot_snapshot

_MAX_RESPONSE_BYTES = 16 * 1024 * 1024
_PAGES_PER_SYNC = 3
_HOSTS = {
    "goszakupki_by": "goszakupki.by",
    "gias_by": "gias.by",
    "icetrade_by": "icetrade.by",
    "butb_by": "zakupki.butb.by",
}
logger = logging.getLogger(__name__)


def _source_url(publication: MarketPublicationInput) -> str | None:
    try:
        parts = urlsplit(publication.url)
        host = parts.hostname or ""
        if parts.scheme != "https" or parts.username is not None or parts.password is not None or parts.port not in {None, 443}:
            return None
    except ValueError:
        return None
    expected = _HOSTS[publication.source]
    return publication.url if host == expected or host.endswith(f".{expected}") else None


async def _pull_page(cursor: str | None) -> MarketPageInput:
    root = settings.BELZAKUPKI_API_BASE_URL.rstrip("/")
    params = {"limit": 100}
    if cursor:
        params["cursor"] = cursor
    timeout = settings.BELZAKUPKI_IMPORT_TIMEOUT_SECONDS
    headers = {"Authorization": f"Bearer {settings.BELZAKUPKI_INTEGRATION_KEY}", "Accept-Encoding": "identity"}
    async with asyncio.timeout(timeout), httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        async with client.stream("GET", f"{root}/api/v1/tender-market/publications", params=params, headers=headers) as response:
            response.raise_for_status()
            if response.headers.get("content-encoding", "identity").lower() != "identity":
                raise ValueError("Unexpected market response encoding")
            body = bytearray()
            async for chunk in response.aiter_raw():
                if len(body) + len(chunk) > _MAX_RESPONSE_BYTES:
                    raise ValueError("Market feed response exceeds the page size limit")
                body.extend(chunk)
    return MarketPageInput.model_validate_json(body)


class TenderMarketSyncService:
    @staticmethod
    def enabled() -> bool:
        return bool(settings.BELZAKUPKI_TENDER_MARKET_ENABLED
                    and settings.BELZAKUPKI_API_BASE_URL.strip() and settings.BELZAKUPKI_INTEGRATION_KEY)

    @staticmethod
    async def run_scheduled_sync() -> None:
        for _ in range(_PAGES_PER_SYNC):
            if not await TenderMarketSyncService._sync_page():
                break

    @staticmethod
    async def _sync_page() -> bool:
        async with async_session_maker() as db:
            checkpoint = await TenderMarketDAO.checkpoint(db)
            token = (checkpoint.cursor, checkpoint.generation)
        try:
            page = await _pull_page(token[0])
        except httpx.HTTPStatusError as error:
            if token[0] is None or error.response.status_code != 400:
                raise
            # The producer binds cursors to its configured market profile set.
            # Start a new whole sweep before retiring any previously seen notice.
            async with async_session_maker() as db, db.begin():
                current = await TenderMarketDAO.checkpoint(db, lock=True)
                if (current.cursor, current.generation) == token:
                    current.cursor = None
                    current.generation += 1
            return False
        async with async_session_maker() as db, db.begin():
            stored = await TenderMarketSyncService.store_page(db, token, page)
            return stored and page.has_more

    @staticmethod
    async def store_page(
        session: AsyncSession, token: tuple[str | None, int], page: MarketPageInput,
    ) -> bool:
        checkpoint = await TenderMarketDAO.checkpoint(session, lock=True)
        if (checkpoint.cursor, checkpoint.generation) != token:
            return False
        if page.has_more and page.next_cursor == checkpoint.cursor:
            raise ValueError("Market cursor did not advance")
        incoming: dict[tuple[str, str], tuple[MarketPublicationInput, str]] = {}
        for row in page.items:
            try:
                item = MarketPublicationInput.model_validate(row)
            except ValidationError:
                continue
            source_url = _source_url(item)
            key = item.source, item.external_id
            if source_url and (key not in incoming or item.updated_at >= incoming[key][0].updated_at):
                incoming[key] = (item, source_url)
        stored = {(row.source, row.external_id): row for row in await TenderMarketDAO.publications(session, list(incoming))}
        for key, (item, source_url) in incoming.items():
            row = stored.get(key)
            if row is None:
                row = TenderMarketPublication(source=item.source, external_id=item.external_id)
            row.seen_generation = checkpoint.generation
            updated = row.provider_updated_at
            if updated is None or item.updated_at >= _as_utc(updated):
                row.title = item.title
                row.source_url = source_url
                row.canonical_url = canonical_procurement_url(item.canonical_url)
                row.provider_updated_at = item.updated_at
                row.published_at = item.published_at
                row.deadline_at = item.deadline_at
                row.active = item.active
                row.lot_snapshot = native_lot_snapshot(item.model_dump())
            session.add(row)
        if not page.has_more:
            await session.flush()
            await TenderMarketDAO.deactivate_unseen(session, checkpoint.generation)
            checkpoint.generation += 1
            checkpoint.completed_at = datetime.now(timezone.utc)
        checkpoint.cursor = page.next_cursor
        logger.info("Tender market page stored accepted=%d supplied=%d terminal=%s",
                    len(incoming), len(page.items), not page.has_more)
        return True


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
