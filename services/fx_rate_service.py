from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models.content import GlobalConfig


_RATE_CACHE_VALUE: Optional[Decimal] = None
_RATE_CACHE_AT: Optional[datetime] = None
_RATE_CACHE_TTL = timedelta(minutes=10)


def _parse_decimal(value: str | None) -> Optional[Decimal]:
    raw = (value or "").strip().replace(",", ".")
    if not raw:
        return None
    try:
        return Decimal(raw)
    except Exception:
        return None


class FxRateService:
    NBRB_USD_URL = "https://api.nbrb.by/exrates/rates/USD?parammode=2"

    @staticmethod
    async def _get_config(session: AsyncSession, key: str) -> Optional[GlobalConfig]:
        res = await session.execute(select(GlobalConfig).where(GlobalConfig.key == key))
        return res.scalar_one_or_none()

    @staticmethod
    async def _get_manual_rate(session: AsyncSession) -> Optional[Decimal]:
        cfg = await FxRateService._get_config(session, "fx_rate_usd_byn")
        return _parse_decimal(cfg.value if cfg else None)

    @staticmethod
    async def _get_rate_source(session: AsyncSession) -> str:
        cfg = await FxRateService._get_config(session, "fx_rate_source")
        value = (cfg.value if cfg else "manual").strip().lower()
        return value if value in {"manual", "nbrb"} else "manual"

    @staticmethod
    async def _get_supplier_markup_pct(session: AsyncSession) -> Decimal:
        cfg = await FxRateService._get_config(session, "fx_supplier_markup_percent")
        parsed = _parse_decimal(cfg.value if cfg else None)
        if parsed is None:
            return Decimal("2.0")
        # Guardrail for obviously invalid values.
        if parsed < Decimal("0"):
            return Decimal("0")
        if parsed > Decimal("100"):
            return Decimal("100")
        return parsed

    @staticmethod
    async def _fetch_nbrb_usd_rate() -> Optional[Decimal]:
        global _RATE_CACHE_VALUE, _RATE_CACHE_AT

        now = datetime.now()
        if _RATE_CACHE_VALUE is not None and _RATE_CACHE_AT is not None:
            if now - _RATE_CACHE_AT <= _RATE_CACHE_TTL:
                return _RATE_CACHE_VALUE

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(FxRateService.NBRB_USD_URL)
                resp.raise_for_status()
                data = resp.json()
                rate = data.get("Cur_OfficialRate")
                parsed = _parse_decimal(str(rate) if rate is not None else None)
                if parsed is not None:
                    _RATE_CACHE_VALUE = parsed
                    _RATE_CACHE_AT = now
                return parsed
        except Exception:
            return None

    @staticmethod
    async def get_effective_usd_byn_rate(session: AsyncSession) -> Optional[Decimal]:
        source = await FxRateService._get_rate_source(session)
        manual = await FxRateService._get_manual_rate(session)
        if source == "manual":
            return manual

        nbrb_rate = await FxRateService._fetch_nbrb_usd_rate()
        # Fallback to manual if NBRB temporarily unavailable.
        return nbrb_rate if nbrb_rate is not None else manual

    @staticmethod
    async def get_supplier_usd_byn_rate(session: AsyncSession) -> Optional[Decimal]:
        base = await FxRateService.get_effective_usd_byn_rate(session)
        if base is None:
            return None
        markup_pct = await FxRateService._get_supplier_markup_pct(session)
        multiplier = Decimal("1") + (markup_pct / Decimal("100"))
        return (base * multiplier).quantize(Decimal("0.0001"))
