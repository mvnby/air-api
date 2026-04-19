from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models.content import GlobalConfig


_RATE_CACHE_VALUE_USD: Optional[Decimal] = None
_RATE_CACHE_VALUE_EUR: Optional[Decimal] = None
_RATE_CACHE_VALUE_RUB: Optional[Decimal] = None
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
    NBRB_EUR_URL = "https://api.nbrb.by/exrates/rates/EUR?parammode=2"
    NBRB_RUB_URL = "https://api.nbrb.by/exrates/rates/RUB?parammode=2"

    @staticmethod
    async def _get_config(session: AsyncSession, key: str) -> Optional[GlobalConfig]:
        res = await session.execute(select(GlobalConfig).where(GlobalConfig.key == key))
        return res.scalar_one_or_none()

    @staticmethod
    async def _get_manual_usd_rate(session: AsyncSession) -> Optional[Decimal]:
        cfg = await FxRateService._get_config(session, "fx_rate_usd_byn")
        return _parse_decimal(cfg.value if cfg else None)

    @staticmethod
    async def _get_manual_rub_rate(session: AsyncSession) -> Optional[Decimal]:
        cfg = await FxRateService._get_config(session, "fx_rate_rub_byn")
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
    def _parse_nbrb_rate_payload(payload: dict | None) -> Optional[Decimal]:
        data = payload or {}
        rate_raw = data.get("Cur_OfficialRate")
        scale_raw = data.get("Cur_Scale", 1)
        rate = _parse_decimal(str(rate_raw) if rate_raw is not None else None)
        scale = _parse_decimal(str(scale_raw) if scale_raw is not None else "1")
        if rate is None or scale is None or scale == 0:
            return None
        return (rate / scale).quantize(Decimal("0.0001"))

    @staticmethod
    async def _fetch_nbrb_rates() -> tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
        global _RATE_CACHE_VALUE_USD, _RATE_CACHE_VALUE_EUR, _RATE_CACHE_VALUE_RUB, _RATE_CACHE_AT

        now = datetime.now()
        if _RATE_CACHE_AT is not None:
            if now - _RATE_CACHE_AT <= _RATE_CACHE_TTL:
                return _RATE_CACHE_VALUE_USD, _RATE_CACHE_VALUE_EUR, _RATE_CACHE_VALUE_RUB

        usd_val = None
        eur_val = None
        rub_val = None

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                usd_resp = await client.get(FxRateService.NBRB_USD_URL)
                if usd_resp.status_code == 200:
                    usd_val = FxRateService._parse_nbrb_rate_payload(usd_resp.json())

                eur_resp = await client.get(FxRateService.NBRB_EUR_URL)
                if eur_resp.status_code == 200:
                    eur_val = FxRateService._parse_nbrb_rate_payload(eur_resp.json())

                rub_resp = await client.get(FxRateService.NBRB_RUB_URL)
                if rub_resp.status_code == 200:
                    rub_val = FxRateService._parse_nbrb_rate_payload(rub_resp.json())

                _RATE_CACHE_VALUE_USD = usd_val
                _RATE_CACHE_VALUE_EUR = eur_val
                _RATE_CACHE_VALUE_RUB = rub_val
                _RATE_CACHE_AT = now
        except Exception:
            pass

        return usd_val, eur_val, rub_val

    @staticmethod
    async def get_effective_usd_byn_rate(session: AsyncSession) -> Optional[Decimal]:
        source = await FxRateService._get_rate_source(session)
        manual = await FxRateService._get_manual_usd_rate(session)
        if source == "manual":
            return manual

        usd_rate, _, _ = await FxRateService._fetch_nbrb_rates()
        # Fallback to manual if NBRB temporarily unavailable.
        return usd_rate if usd_rate is not None else manual

    @staticmethod
    async def get_effective_eur_byn_rate(session: AsyncSession) -> Optional[Decimal]:
        source = await FxRateService._get_rate_source(session)
        # We only have manual override for USD currently, so if we can't fetch EUR, we return None
        if source == "manual":
            return None

        _, eur_rate, _ = await FxRateService._fetch_nbrb_rates()
        return eur_rate

    @staticmethod
    async def get_effective_rub_byn_rate(session: AsyncSession) -> Optional[Decimal]:
        source = await FxRateService._get_rate_source(session)
        manual = await FxRateService._get_manual_rub_rate(session)
        if source == "manual" and manual is not None:
            return manual

        _, _, rub_rate = await FxRateService._fetch_nbrb_rates()
        # Fallback chain: NBRB -> manual.
        return rub_rate if rub_rate is not None else manual

    @staticmethod
    async def get_supplier_usd_byn_rate(session: AsyncSession) -> Optional[Decimal]:
        base = await FxRateService.get_effective_usd_byn_rate(session)
        if base is None:
            return None
        markup_pct = await FxRateService._get_supplier_markup_pct(session)
        multiplier = Decimal("1") + (markup_pct / Decimal("100"))
        return (base * multiplier).quantize(Decimal("0.0001"))
