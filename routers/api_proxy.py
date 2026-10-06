"""Belarus proxy endpoints split from the main API router."""

from datetime import datetime, timedelta
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from core.security import get_current_username
from schemas import AddressSuggestResponse
from services.address_suggest_service import AddressSuggestService
from services.belarus_registry_service import fetch_registry_data

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
    try:
        return await fetch_registry_data(unp)
    except ValueError:
        raise HTTPException(status_code=422, detail="УНП должен содержать 9 цифр") from None


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
    """
    Look up Belarus registry requisites by a nine-digit UNP. Requires Manager
    authentication; invalid UNP returns 422. Data comes from the shared external registry,
    not tenant CRM records.
    """
    return await _fetch_egr_data(unp)


@router.get("/admin/proxy/bank")
async def find_bank(
    search: str = Query(None, description="BIC код или IBAN"),
    username: str = Depends(get_current_username),
):
    """
    Read the shared NBRB bank reference, optionally matching BIC or Belarus IBAN. Requires
    Manager authentication. Without search returns the bank list; a miss is an error object
    with HTTP 200. Reference data uses a 72-hour in-process cache and can fall back to
    cached data on fetch exceptions.
    """
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
    """
    Public Belarus registry lookup by a nine-digit UNP (422 for invalid format). No Manager
    token or storefront signature is required: this is an explicit gateway exception. Reads
    shared external registry data, not tenant records.
    """
    return await _fetch_egr_data(unp)


@router.get("/v1/proxy/bank")
async def public_find_bank(search: str = Query(None, description="BIC код или IBAN")):
    """
    Public bank lookup by BIC or Belarus IBAN. No Manager token or storefront signature is
    required: this is an explicit gateway exception. Empty search returns []; a miss returns
    an error object with HTTP 200. Uses the shared cached NBRB reference.
    """
    if not search:
        return []

    target_bic, bic_from_iban = _normalize_bank_search_query(search)
    banks = await get_all_banks()
    found_bank = _find_best_bank_match(banks, target_bic, bic_from_iban)

    if found_bank:
        return _extract_bank_response(found_bank)

    return {"error": "Банк не найден"}


@router.get("/v1/address-suggest", response_model=AddressSuggestResponse, operation_id="public_address_suggest")
async def public_address_suggest(q: str = Query(..., min_length=2)):
    """
    Public address suggestions for a query of at least two characters. No Manager token or
    storefront signature is required: this is an explicit gateway exception. Returns an
    empty items list when suggestions are disabled or the upstream HTTP request fails.
    """
    try:
        items = await AddressSuggestService.suggest(q)
    except RuntimeError as exc:
        logger.warning("Public address suggest disabled: %s", exc)
        items = []
    except httpx.HTTPError:
        logger.exception("Public Yandex address suggest failed")
        items = []

    return AddressSuggestResponse(items=items)
