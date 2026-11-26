"""Apply only the current company's saved profiles to the shared public feed."""

import asyncio
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from crud.tender_market import TenderMarketDAO
from models import TenderMarketPublication
from models.tenancy import TenantScope
from schemas_tender_market import TenderMarketItem, TenderMarketProfileMatch, TenderMarketResults
from services.tender_module_service import TenderModuleError, TenderModuleService
from services.tender_profile_preview import match_publication_signals, publication_signals

_BATCH_SIZE = 100
_MAX_BATCHES = 4


def _decide(row, profiles) -> list[TenderMarketProfileMatch]:
    tender = {"source": row.source, **row.lot_snapshot}
    signals = publication_signals(row.title, tender, active_lots_only=True)
    matches = []
    for profile in profiles:
        result, lots = match_publication_signals(signals, profile)
        if result.state != "excluded":
            matches.append(TenderMarketProfileMatch(name=profile.name, result=result, lots=lots))
    return matches


def _matching_batch(rows, profiles, desired: str, limit: int):
    result = []
    for row in rows:
        matches = _decide(row, profiles)
        state = "match" if any(item.result.state == "match" for item in matches) else "review"
        if state == desired and matches:
            result.append((row, matches))
            if len(result) == limit:
                return result, row.id
    return result, rows[-1].id if rows else None


class TenderMarketService:
    @staticmethod
    async def visible_publication(session: AsyncSession, scope: TenantScope, publication_id: int) -> TenderMarketPublication:
        settings = await TenderModuleService.get(session, scope.tenant_id)
        if scope.demo_read_only or not settings.enabled or not settings.entitled:
            raise TenderModuleError(403, "Подключите модуль тендеров в настройках компании.")
        row = await TenderMarketDAO.get(session, publication_id)
        if (row is None or not row.active or row.deadline_at and _aware(row.deadline_at) <= datetime.now(timezone.utc)
                or not await asyncio.to_thread(_decide, row, settings.profiles)):
            raise TenderModuleError(404, "Публикация недоступна для профилей компании.")
        current = await TenderModuleService.get(session, scope.tenant_id)
        if current.version != settings.version or not current.enabled or not current.entitled:
            raise TenderModuleError(409, "Настройки модуля изменились. Обновите выдачу.")
        return row

    @staticmethod
    async def list(
        session: AsyncSession, scope: TenantScope, *, desired: Literal["match", "review"],
        profile_name: str | None, before_id: int | None, settings_version: int | None, limit: int,
    ) -> TenderMarketResults:
        settings = await TenderModuleService.get(session, scope.tenant_id)
        if scope.demo_read_only or not settings.enabled or not settings.entitled:
            raise TenderModuleError(403, "Подключите модуль тендеров в настройках компании.")
        if before_id is not None and settings.version != settings_version:
            raise TenderModuleError(409, "Профили изменились. Обновите выдачу.")
        profiles = [profile for profile in settings.profiles if profile_name is None or profile.name == profile_name]
        if not profiles:
            raise TenderModuleError(404, "Профиль поиска не найден.")
        now = datetime.now(timezone.utc)
        entries = []
        next_id = before_id
        for _ in range(_MAX_BATCHES):
            rows = await TenderMarketDAO.candidates(session, before_id=next_id, now=now, limit=_BATCH_SIZE)
            batch, next_id = await asyncio.to_thread(_matching_batch, rows, profiles, desired, limit - len(entries))
            for row, profiles_match in batch:
                entries.append(TenderMarketItem(
                    id=row.id, title=row.title, source=row.source, source_url=row.source_url,
                    deadline_at=_aware(row.deadline_at), profiles=profiles_match,
                ))
            if len(entries) == limit:
                if len(rows) < _BATCH_SIZE and next_id == rows[-1].id:
                    next_id = None
                break
            if len(rows) < _BATCH_SIZE:
                next_id = None
                break
        latest = await TenderMarketDAO.checkpoint(session)
        current = await TenderModuleService.get(session, scope.tenant_id)
        if current.version != settings.version or not current.enabled or not current.entitled:
            raise TenderModuleError(409, "Настройки модуля изменились. Обновите выдачу.")
        return TenderMarketResults(
            items=entries, next_before_id=next_id, settings_version=settings.version,
            profile_names=[profile.name for profile in settings.profiles],
            last_sync_at=_aware(latest.completed_at), syncing=latest.cursor is not None,
        )


def _aware(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value
