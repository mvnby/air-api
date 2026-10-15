"""Read-only adapter for the public address suggestions used by belpost.by."""

import re

import httpx
from pydantic import BaseModel, ConfigDict, Field


class PostcodeSearchPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    address: str = Field(min_length=3, max_length=600)


class PostcodeSuggestion(BaseModel):
    postal_code: str
    address: str
    buildings: str


class PostcodeSearchResponse(BaseModel):
    items: list[PostcodeSuggestion]
    source: str = "Белпочта"


class PostcodeLookupUnavailable(ValueError):
    pass


async def lookup_postcodes(address: str) -> PostcodeSearchResponse:
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:
            response = await client.get(
                "https://api.belpost.by/api/v1/postcodes/autocomplete",
                params={"search": address},
            )
            response.raise_for_status()
            rows = response.json()
        if not isinstance(rows, list):
            raise ValueError("Unexpected Belpost response")
        items: list[PostcodeSuggestion] = []
        seen: set[tuple[str, str, str]] = set()
        for row in rows[:100]:
            if not isinstance(row, dict):
                continue
            code = str(row.get("postcode") or "")
            label = row.get("short_address") or row.get("autocomplete_address")
            buildings = row.get("buildings") or ""
            if not re.fullmatch(r"[0-9]{6}", code) or not isinstance(label, str) or not isinstance(buildings, str):
                continue
            identity = (code, label, buildings)
            if identity in seen:
                continue
            seen.add(identity)
            items.append(PostcodeSuggestion(postal_code=code, address=label[:1000], buildings=buildings[:6000]))
        return PostcodeSearchResponse(items=items)
    except (httpx.HTTPError, ValueError) as exc:
        raise PostcodeLookupUnavailable(
            "Справочник Белпочты сейчас недоступен. Укажите индекс вручную или откройте сайт Белпочты."
        ) from exc
