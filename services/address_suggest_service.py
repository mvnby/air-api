"""Service helpers for address autocomplete providers."""

from __future__ import annotations

import os
import re
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
    async def suggest(
        cls,
        query: str,
        *,
        ull: str | None = None,
    ) -> list[dict[str, str | None]]:
        items: list[dict[str, str | None]] = []
        seen_values: set[str] = set()

        scopes = (
            [(cls.BELARUS_BBOX, ull)]
            if ull
            else [
                (cls.VITEBSK_REGION_BBOX, None),
                (cls.BELARUS_BBOX, None),
            ]
        )
        for bbox, scope_ull in scopes:
            payload = await cls.fetch_raw(
                query,
                bbox=bbox,
                ull=scope_ull,
                strict_bounds=True,
            )
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
            value = cls._compose_value(result, title, subtitle)
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

    @classmethod
    def _compose_value(cls, result: dict[str, Any], title: str | None, subtitle: str | None) -> str | None:
        structured = cls._compose_structured_value(result, title=title, subtitle=subtitle)
        if structured:
            return structured
        return cls._compose_fallback_value(title, subtitle)

    @classmethod
    def _compose_structured_value(cls, result: dict[str, Any], *, title: str | None, subtitle: str | None) -> str | None:
        components = cls._extract_address_components(result)
        if not components:
            components = cls._parse_title_subtitle(title, subtitle)

        object_name = components.get("object")
        district = components.get("district")
        council = components.get("council")
        city = components.get("city")
        street = components.get("street")
        house = components.get("house")

        parts = cls._dedupe_parts(
            [
                object_name,
                district,
                council,
                city,
                street,
                f"д. {house}" if house else None,
            ]
        )
        if city and (street or house):
            return ", ".join(parts)
        return None

    @classmethod
    def _extract_address_components(cls, result: dict[str, Any]) -> dict[str, str]:
        components = cls._find_component_list(result)
        if not components:
            return {}

        parsed: dict[str, str] = {}
        city_type_names = {
            "locality",
            "settlement",
        }
        street_type_names = {"street"}
        house_type_names = {"house", "house_number", "premise"}

        for component in components:
            if not isinstance(component, dict):
                continue
            name = cls._component_name(component)
            if not name:
                continue
            kinds = cls._component_kinds(component)
            lowered_name = name.lower()
            if not parsed.get("district") and "район" in lowered_name:
                parsed["district"] = name
            elif not parsed.get("council") and "сельсовет" in lowered_name:
                parsed["council"] = name
            elif not parsed.get("city") and kinds & city_type_names:
                parsed["city"] = name
            elif not parsed.get("street") and kinds & street_type_names:
                parsed["street"] = name
            elif not parsed.get("house") and kinds & house_type_names:
                parsed["house"] = cls._normalize_house(name)

        title = cls._extract_text(result.get("title")) or ""
        if parsed.get("city") and parsed.get("street") and parsed.get("house"):
            title_without_address = cls._strip_address_from_title(title, parsed)
            if title_without_address:
                parsed["object"] = title_without_address

        return parsed

    @classmethod
    def _find_component_list(cls, value: Any) -> list[Any]:
        if isinstance(value, list):
            if any(isinstance(item, dict) and cls._component_name(item) for item in value):
                return value
            for item in value:
                nested = cls._find_component_list(item)
                if nested:
                    return nested
        if isinstance(value, dict):
            for key in ("components", "Components", "address_components", "AddressComponents"):
                nested = value.get(key)
                if isinstance(nested, list):
                    return nested
            for nested in value.values():
                found = cls._find_component_list(nested)
                if found:
                    return found
        return []

    @classmethod
    def _parse_title_subtitle(cls, title: str | None, subtitle: str | None) -> dict[str, str]:
        title_parts = cls._split_parts(title)
        subtitle_parts = cls._split_parts(subtitle)
        if not title_parts and not subtitle_parts:
            return {}

        house = cls._extract_house(title_parts)
        street = cls._extract_street(title_parts)
        city = cls._extract_city(subtitle_parts) or cls._extract_city(title_parts)

        object_name = cls._extract_object_name(
            title_parts=title_parts,
            subtitle_parts=subtitle_parts,
            address_values=[city, street, house, *cls._extract_admin_parts(subtitle_parts)],
            street=street,
        )
        result: dict[str, str] = {}
        if object_name:
            result["object"] = object_name
        for part in cls._extract_admin_parts(subtitle_parts):
            if "район" in part.lower() and not result.get("district"):
                result["district"] = part
            elif "сельсовет" in part.lower() and not result.get("council"):
                result["council"] = part
        if city:
            result["city"] = city
        if street:
            result["street"] = street
        if house:
            result["house"] = house
        return result

    @staticmethod
    def _split_parts(value: str | None) -> list[str]:
        return [part.strip() for part in (value or "").split(",") if part.strip()]

    @classmethod
    def _extract_house(cls, parts: list[str]) -> str | None:
        for part in parts:
            normalized = cls._normalize_house(part)
            if normalized and cls._looks_like_house(part):
                return normalized
        return None

    @staticmethod
    def _extract_street(parts: list[str]) -> str | None:
        street_markers = (
            "улица",
            "ул.",
            "проспект",
            "пр-т",
            "переулок",
            "пер.",
            "проезд",
            "тракт",
            "шоссе",
            "бульвар",
            "площадь",
            "набережная",
        )
        for part in parts:
            lowered = part.lower()
            if any(marker in lowered for marker in street_markers):
                return part
        return None

    @staticmethod
    def _extract_city(parts: list[str]) -> str | None:
        skip_markers = (
            "район",
            "область",
            "сельсовет",
            "вобласць",
            "беларусь",
            "республика",
            "улица",
            "ул.",
            "проспект",
            "пр-т",
            "переулок",
            "пер.",
            "проезд",
            "тракт",
            "шоссе",
            "бульвар",
            "площадь",
            "набережная",
        )
        for part in parts:
            lowered = part.lower()
            if any(marker in lowered for marker in skip_markers):
                continue
            if AddressSuggestService._looks_like_house(part):
                continue
            if re.match(r"^(г\.|город)\s+", lowered):
                return re.sub(r"^(г\.|город)\s+", "", part, flags=re.IGNORECASE).strip()
            return part
        return None

    @staticmethod
    def _extract_admin_parts(parts: list[str]) -> list[str]:
        result: list[str] = []
        for part in parts:
            lowered = part.lower()
            if "район" in lowered or "сельсовет" in lowered:
                result.append(part)
        return result

    @classmethod
    def _extract_object_name(
        cls,
        *,
        title_parts: list[str],
        subtitle_parts: list[str],
        address_values: list[str | None],
        street: str | None,
    ) -> str | None:
        address_value_set = {value for value in address_values if value}
        for part in title_parts + subtitle_parts:
            normalized_house = cls._normalize_house(part)
            if part in address_value_set or normalized_house in address_value_set:
                continue
            if street and part == street:
                continue
            lowered = part.lower()
            if any(marker in lowered for marker in ("улица", "ул.", "район", "область", "сельсовет", "беларусь")):
                continue
            if cls._looks_like_house(part):
                continue
            return part
        return None

    @staticmethod
    def _component_name(component: dict[str, Any]) -> str | None:
        for key in ("name", "Name", "text", "Text", "value", "Value"):
            value = component.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _component_kinds(component: dict[str, Any]) -> set[str]:
        raw_values: list[Any] = []
        for key in ("kind", "Kind", "type", "Type", "kinds", "Kinds", "types", "Types"):
            value = component.get(key)
            if value is not None:
                raw_values.append(value)
        kinds: set[str] = set()
        for raw in raw_values:
            if isinstance(raw, str):
                kinds.add(raw.strip().lower())
            elif isinstance(raw, list):
                kinds.update(str(item).strip().lower() for item in raw if str(item).strip())
        return kinds

    @staticmethod
    def _looks_like_house(value: str) -> bool:
        return bool(re.match(r"^(д\.?\s*)?\d+[а-яa-z0-9/-]*$", value.strip(), re.IGNORECASE))

    @staticmethod
    def _normalize_house(value: str) -> str | None:
        text = value.strip()
        match = re.match(r"^(?:д\.?\s*)?(.+)$", text, flags=re.IGNORECASE)
        if not match:
            return None
        house = match.group(1).strip()
        return house if re.match(r"^\d+[а-яa-z0-9/-]*$", house, re.IGNORECASE) else None

    @classmethod
    def _strip_address_from_title(cls, title: str, parsed: dict[str, str]) -> str | None:
        parts = cls._split_parts(title)
        if not parts:
            return None
        address_values = {value for value in (parsed.get("city"), parsed.get("street"), parsed.get("house")) if value}
        for part in parts:
            normalized_house = cls._normalize_house(part)
            if part in address_values or normalized_house in address_values:
                continue
            if parsed.get("street") and part == parsed["street"]:
                continue
            if cls._looks_like_house(part):
                continue
            return part
        return None

    @staticmethod
    def _dedupe_parts(parts: list[str | None]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for part in parts:
            if not part:
                continue
            key = part.casefold()
            if key in seen:
                continue
            seen.add(key)
            result.append(part)
        return result

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
    def _compose_fallback_value(title: str | None, subtitle: str | None) -> str | None:
        parts: list[str] = []
        for part in (title, subtitle):
            if not part:
                continue
            if part not in parts:
                parts.append(part)
        if not parts:
            return None
        return ", ".join(parts)
