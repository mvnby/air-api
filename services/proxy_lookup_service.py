"""Service-layer helpers for public/admin proxy lookups."""

from datetime import datetime, timedelta
import logging

import httpx


logger = logging.getLogger(__name__)


class ProxyLookupService:
    BANK_CACHE = {
        "data": [],
        "last_updated": None,
    }

    @staticmethod
    async def fetch_egr_data(unp: str) -> dict:
        url = f"http://grp.nalog.gov.by/api/grp-public/data?unp={unp}&type=json&charset=UTF-8"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, timeout=10.0)
                return response.json()
            except Exception as e:
                return {"error": str(e)}

    @staticmethod
    async def get_all_banks() -> list[dict]:
        """Fetch NBRB banks list with 72h cache."""
        now = datetime.now()
        if ProxyLookupService.BANK_CACHE["data"] and ProxyLookupService.BANK_CACHE["last_updated"]:
            if now - ProxyLookupService.BANK_CACHE["last_updated"] < timedelta(hours=72):
                return ProxyLookupService.BANK_CACHE["data"]

        url = "https://api.nbrb.by/bic"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    ProxyLookupService.BANK_CACHE["data"] = data
                    ProxyLookupService.BANK_CACHE["last_updated"] = now
                    return data
            except Exception as e:
                logger.error(f"Error fetching banks: {e}")
                return ProxyLookupService.BANK_CACHE["data"]
        return []

    @staticmethod
    def _normalize_bank_search_query(search: str) -> tuple[str, str | None]:
        query = search.strip().replace(" ", "").upper()
        bic_from_iban = query[4:8] if len(query) >= 8 and query.startswith("BY") else None
        return query, bic_from_iban

    @staticmethod
    def _extract_bank_response(bank: dict) -> dict:
        return {
            "name": bank.get("NmBankShort"),
            "address": bank.get("AdrBank"),
            "bic": bank.get("CDBank"),
            "swift": bank.get("CDBank"),
        }

    @staticmethod
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

    @staticmethod
    async def find_bank(search: str | None, *, include_all_on_empty: bool, include_debug: bool = False):
        if not search:
            return await ProxyLookupService.get_all_banks() if include_all_on_empty else []

        target_bic, bic_from_iban = ProxyLookupService._normalize_bank_search_query(search)
        banks = await ProxyLookupService.get_all_banks()
        found_bank = ProxyLookupService._find_best_bank_match(banks, target_bic, bic_from_iban)

        if found_bank:
            return ProxyLookupService._extract_bank_response(found_bank)

        payload = {"error": "Банк не найден"}
        if include_debug:
            payload["debug_bic"] = bic_from_iban or target_bic
        return payload
