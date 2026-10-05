"""Shared read-only access to Belarus's public taxpayer registry."""

import httpx

from core.input_validation import validate_optional_unp


async def fetch_registry_data(unp: str) -> dict:
    normalized = validate_optional_unp(unp)
    if normalized is None:
        return {"error": "Укажите УНП"}
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            response = await client.get(
                "http://grp.nalog.gov.by/api/grp-public/data",
                params={"unp": normalized, "type": "json", "charset": "UTF-8"},
            )
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {"error": "Некорректный ответ реестра"}
        except (httpx.HTTPError, ValueError):
            return {"error": "Реестр временно недоступен"}
