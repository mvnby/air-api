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


@router.get("/admin/proxy/egr")
async def proxy_egr(
    unp: str,
    username: str = Depends(get_current_username),
):
    """Proxy for Belarus EGR (Ministry of Taxes) API."""
    url = f"http://grp.nalog.gov.by/api/grp-public/data?unp={unp}&type=json&charset=UTF-8"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=10.0)
            return response.json()
        except Exception as e:
            return {"error": str(e)}


@router.get("/admin/proxy/bank")
async def find_bank(
    search: str = Query(None, description="BIC код или IBAN"),
    username: str = Depends(get_current_username),
):
    """Find bank in NBRB reference by BIC/IBAN."""
    if not search:
        return await get_all_banks()

    query = search.strip().replace(" ", "").upper()
    target_bic = query
    banks = await get_all_banks()

    found_bank = None
    bic_from_iban = None
    if len(query) >= 8 and query.startswith("BY"):
        bic_from_iban = query[4:8]

    for bank in banks:
        cd_bank = bank.get("CDBank", "")
        is_active = bank.get("DtEnd") is None

        if cd_bank == target_bic:
            if is_active:
                found_bank = bank
                break
            if not found_bank:
                found_bank = bank

        if bic_from_iban and cd_bank.startswith(bic_from_iban):
            if is_active:
                found_bank = bank
                break
            if not found_bank:
                found_bank = bank

    if found_bank:
        return {
            "name": found_bank.get("NmBankShort"),
            "address": found_bank.get("AdrBank"),
            "bic": found_bank.get("CDBank"),
            "swift": found_bank.get("CDBank"),
        }

    return {"error": "Банк не найден", "debug_bic": bic_from_iban or target_bic}


@router.get("/v1/proxy/egr")
async def public_proxy_egr(unp: str):
    """Public proxy for Belarus EGR (Ministry of Taxes) API."""
    url = f"http://grp.nalog.gov.by/api/grp-public/data?unp={unp}&type=json&charset=UTF-8"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=10.0)
            return response.json()
        except Exception as e:
            return {"error": str(e)}


@router.get("/v1/proxy/bank")
async def public_find_bank(search: str = Query(None, description="BIC код или IBAN")):
    """Public proxy to find bank details by IBAN/BIC."""
    if not search:
        return []

    query = search.strip().replace(" ", "").upper()
    target_bic = query
    banks = await get_all_banks()
    found_bank = None

    bic_from_iban = None
    if len(query) >= 8 and query.startswith("BY"):
        bic_from_iban = query[4:8]

    for bank in banks:
        cd_bank = bank.get("CDBank", "")
        is_active = bank.get("DtEnd") is None

        if cd_bank == target_bic:
            if is_active:
                found_bank = bank
                break
            if not found_bank:
                found_bank = bank

        if bic_from_iban and cd_bank.startswith(bic_from_iban):
            if is_active:
                found_bank = bank
                break
            if not found_bank:
                found_bank = bank

    if found_bank:
        return {
            "name": found_bank.get("NmBankShort"),
            "address": found_bank.get("AdrBank"),
            "bic": found_bank.get("CDBank"),
            "swift": found_bank.get("CDBank"),
        }

    return {"error": "Банк не найден"}
