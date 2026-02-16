"""Belarus proxy endpoints split from the main API router."""

from datetime import datetime, timedelta
import logging

import httpx
from fastapi import APIRouter, Depends, Query

from core.security import get_current_username

router = APIRouter(tags=["api"])
logger = logging.getLogger(__name__)


# Simple in-memory cache to avoid hammering NBRB on every request.
BANK_CACHE = {
    "data": [],
    "last_updated": None,
}


async def get_all_banks():
    """Fetch NBRB banks list with 72h cache."""
    now = datetime.now()
    if BANK_CACHE["data"] and BANK_CACHE["last_updated"]:
        if now - BANK_CACHE["last_updated"] < timedelta(hours=72):
            return BANK_CACHE["data"]

    url = "https://api.nbrb.by/bic"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                BANK_CACHE["data"] = data
                BANK_CACHE["last_updated"] = now
                return data
        except Exception as e:
            logger.error(f"Error fetching banks: {e}")
            return BANK_CACHE["data"]
    return []


async def _fetch_egr_data(unp: str) -> dict:
    url = f"http://grp.nalog.gov.by/api/grp-public/data?unp={unp}&type=json&charset=UTF-8"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=10.0)
            return response.json()
        except Exception as e:
            return {"error": str(e)}


def _normalize_bank_search_query(search: str) -> tuple[str, str | None]:
    query = search.strip().replace(" ", "").upper()
    bic_from_iban = query[4:8] if len(query) >= 8 and query.startswith("BY") else None
    return query, bic_from_iban


def _extract_bank_response(bank: dict) -> dict:
    return {
        "name": bank.get("NmBankShort"),
        "address": bank.get("AdrBank"),
        "bic": bank.get("CDBank"),
        "swift": bank.get("CDBank"),
    }


def _find_best_bank_match(banks: list[dict], target_bic: str, bic_from_iban: str | None) -> dict | None:
    found_bank = None
    for bank in banks:
        cd_bank = bank.get("CDBank", "")
        is_active = bank.get("DtEnd") is None

        if cd_bank == target_bic:
            if is_active:
                return bank
            if not found_bank:
                found_bank = bank

        if bic_from_iban and cd_bank.startswith(bic_from_iban):
            if is_active:
                return bank
            if not found_bank:
                found_bank = bank

    return found_bank


@router.get("/admin/proxy/egr")
async def proxy_egr(
    unp: str,
    username: str = Depends(get_current_username),
):
    """Proxy for Belarus EGR (Ministry of Taxes) API."""
    return await _fetch_egr_data(unp)


@router.get("/admin/proxy/bank")
async def find_bank(
    search: str = Query(None, description="BIC код или IBAN"),
    username: str = Depends(get_current_username),
):
    """Find bank in NBRB reference by BIC/IBAN."""
    if not search:
        return await get_all_banks()

    target_bic, bic_from_iban = _normalize_bank_search_query(search)
    banks = await get_all_banks()
    found_bank = _find_best_bank_match(banks, target_bic, bic_from_iban)

    if found_bank:
        return _extract_bank_response(found_bank)

    return {"error": "Банк не найден", "debug_bic": bic_from_iban or target_bic}


@router.get("/v1/proxy/egr")
async def public_proxy_egr(unp: str):
    """Public proxy for Belarus EGR (Ministry of Taxes) API."""
    return await _fetch_egr_data(unp)


@router.get("/v1/proxy/bank")
async def public_find_bank(search: str = Query(None, description="BIC код или IBAN")):
    """Public proxy to find bank details by IBAN/BIC."""
    if not search:
        return []

    target_bic, bic_from_iban = _normalize_bank_search_query(search)
    banks = await get_all_banks()
    found_bank = _find_best_bank_match(banks, target_bic, bic_from_iban)

    if found_bank:
        return _extract_bank_response(found_bank)

    return {"error": "Банк не найден"}
