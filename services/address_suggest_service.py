"""Service helpers for address autocomplete providers."""

from __future__ import annotations

import os
from typing import Any

import httpx


class AddressSuggestService:
    API_URL = "https://suggest-maps.yandex.ru/v1/suggest"
    MAX_ITEMS = 8
    LANGUAGE = "ru_BY"
    VITEBSK_CENTER = "30.2049,55.1904"
    VITEBSK_REGION_BBOX = "27.4,54.0~31.9,56.4"
    BELARUS_BBOX = "23.1,51.2~32.8,56.3"

    @classmethod
    async def fetch_raw(
        cls,
        query: str,
        *,
        bbox: str | None = None,
        ull: str | None = None,
        strict_bounds: bool = True,
    ) -> dict[str, Any]:
        api_key = os.getenv("YANDEX_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("YANDEX_API_KEY not configured")

        params: dict[str, Any] = {
            "apikey": api_key,
            "text": query,
            "lang": cls.LANGUAGE,
            "results": cls.MAX_ITEMS,
            "print_address": 1,
            "ull": ull or cls.VITEBSK_CENTER,
            "bbox": bbox or cls.BELARUS_BBOX,
        }
        if strict_bounds:
            params["strict_bounds"] = 1

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                cls.API_URL,
                params=params,
            )
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict):
                return payload
            return {}

    @classmethod
    async def suggest(cls, query: str) -> list[dict[str, str | None]]:
        items: list[dict[str, str | None]] = []
        seen_values: set[str] = set()

        for bbox in (cls.VITEBSK_REGION_BBOX, cls.BELARUS_BBOX):
            payload = await cls.fetch_raw(query, bbox=bbox, strict_bounds=True)
            scoped_items = cls.normalize_results(payload)
            for item in scoped_items:
                value = item.get("value")
                if not value or value in seen_values:
                    continue
                seen_values.add(value)
                items.append(item)
                if len(items) >= cls.MAX_ITEMS:
                    return items

        return items

    @classmethod
    def normalize_results(cls, payload: dict[str, Any]) -> list[dict[str, str | None]]:
        results = payload.get("results", [])
        if not isinstance(results, list):
            return []

        items: list[dict[str, str | None]] = []
        seen_values: set[str] = set()

        for result in results:
            if not isinstance(result, dict):
                continue

            title = cls._extract_text(result.get("title")) or cls._extract_text(result.get("displayName"))
            subtitle = cls._extract_text(result.get("subtitle"))
            value = cls._compose_value(title, subtitle)
            if not value or value in seen_values:
                continue

            seen_values.add(value)
            items.append(
                {
                    "title": title or value,
                    "subtitle": subtitle,
                    "value": value,
                }
            )
            if len(items) >= cls.MAX_ITEMS:
                break

        return items

    @staticmethod
    def _extract_text(value: Any) -> str | None:
        if isinstance(value, str):
            text = value.strip()
            return text or None
        if isinstance(value, dict):
            for key in ("text", "name", "value"):
                text = value.get(key)
                if isinstance(text, str) and text.strip():
                    return text.strip()
        return None

    @staticmethod
    def _compose_value(title: str | None, subtitle: str | None) -> str | None:
        parts: list[str] = []
        for part in (title, subtitle):
            if not part:
                continue
            if part not in parts:
                parts.append(part)
        if not parts:
            return None
        return ", ".join(parts)
