from __future__ import annotations

import html
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import httpx
import slugify

from .base import BaseParser


MDV_HOST = "mdv-aircond.ru"
MDV_BASE_URL = "https://mdv-aircond.ru"
MDV_EXPORT_URLS = {
    "household": f"{MDV_BASE_URL}/upload/export/bytovye-split-sistemy_export.json",
    "semi": f"{MDV_BASE_URL}/upload/export/polupromyshlennye-split-sistemy_export.json",
    "multi": f"{MDV_BASE_URL}/upload/export/multisplit-sistemy_export.json",
}
MDV_SITEMAP_URL = f"{MDV_BASE_URL}/sitemap-iblock-11.xml"


_CATALOG_PATH_MARKERS = {
    "household": "/catalog/bytovye-split-sistemy/",
    "semi": "/catalog/polupromyshlennye-split-sistemy/",
    "multi": "/catalog/multisplit-sistemy/",
}


_INDOOR_TYPE_MARKERS = (
    ("кассет", "кассетный"),
    ("каналь", "канальный"),
    ("напольно", "напольно-потолочный"),
    ("потолоч", "напольно-потолочный"),
    ("консол", "напольно-потолочный"),
    ("колон", "колонный"),
    ("настенн", "настенный"),
)


@dataclass(frozen=True)
class MdvCatalogRecord:
    catalog: str
    item: dict[str, Any]
    source_url: str


class MdvCatalogParser(BaseParser):
    """Importer for MDV Bitrix export JSON files and MDV product pages."""

    SOURCE_NAME = "mdv"

    def __init__(self) -> None:
        self._json_cache: dict[str, list[dict[str, Any]]] = {}
        self._sitemap_urls: list[str] | None = None
        self._records_by_url: dict[str, MdvCatalogRecord] | None = None
        self._records_by_fallback: dict[str, MdvCatalogRecord] | None = None
        self._manual_cache: dict[str, list[dict[str, str]]] = {}

    def supports(self, url: str) -> bool:
        normalized = str(url or "").strip()
        if normalized.startswith("mdv-catalog://"):
            return True
        parts = urlsplit(normalized)
        if not parts.netloc.endswith(MDV_HOST):
            return False
        if parts.path.startswith("/upload/export/") and parts.path.endswith("_export.json"):
            return self._catalog_for_export_url(normalized) is not None
        return parts.path.startswith("/catalog/")

    async def get_import_urls(self, url: str) -> list[str]:
        catalog = self._catalog_for_export_url(url)
        if not catalog:
            return [url.strip()]
        records = await self.collect_records(catalogs=[catalog], include_manuals=False)
        return [record.source_url for record in records]

    async def parse(self, url: str) -> dict[str, Any]:
        record = await self._record_for_url(url)
        return await self.build_import_payload(record, include_manuals=True)

    async def collect_records(
        self,
        *,
        catalogs: list[str] | None = None,
        include_manuals: bool = False,
    ) -> list[MdvCatalogRecord]:
        selected = catalogs or list(MDV_EXPORT_URLS.keys())
        records: list[MdvCatalogRecord] = []
        for catalog in selected:
            for item in await self._load_catalog(catalog):
                records.append(
                    MdvCatalogRecord(
                        catalog=catalog,
                        item=item,
                        source_url=await self._source_url_for_item(catalog, item),
                    )
                )
        if include_manuals:
            for record in records:
                await self._manuals_for_url(record.source_url)
        return records

    async def build_import_payload(
        self,
        record: MdvCatalogRecord,
        *,
        include_manuals: bool,
    ) -> dict[str, Any]:
        item = record.item
        props = self._props(item)
        specs = self._build_specs(record)
        title = self._title_for_record(record, specs)
        images = self._gallery_urls(item)
        price = self._price(item)
        cooling_kw = self._first_float(
            props.get("COOLING_NOM") or props.get("COOLING") or specs.get("capacity_cooling_kw")
        )

        payload = {
            "title": title,
            "slug": self._slug_for_record(record),
            "description": self._description(item),
            "price": int(price),
            "price_currency": "RUB",
            "main_image": self._absolute_url(item.get("PREVIEW_PICTURE") or item.get("DETAIL_PICTURE")),
            "images": images,
            "save_gallery": True,
            "require_media_download": True,
            "categories": [],
            "specs": specs,
            "metrics": {
                "area": int(round(cooling_kw * 10)) if cooling_kw else 0,
                "is_inverter": self._is_inverter(record),
                "power_cooling": cooling_kw,
            },
            "related_urls": [],
            "availability": "Каталог MDV",
            "in_stock": True,
            "refresh_title_on_update": True,
            "publish_on_update": True,
            "source_url": record.source_url,
        }
        if include_manuals:
            payload["manuals"] = await self._manuals_for_url(record.source_url)
        return payload

    async def _record_for_url(self, url: str) -> MdvCatalogRecord:
        normalized = self._normalize_url(url)
        if normalized.startswith("mdv-catalog://"):
            records = await self._records_by_fallback_key()
            key = self._fallback_key_from_url(normalized)
            record = records.get(key)
            if record:
                return record
            raise ValueError(f"MDV catalog fallback item was not found: {url}")

        records_by_url = await self._records_by_source_url()
        record = records_by_url.get(normalized)
        if record:
            return record

        # Some callers may pass a URL with or without a trailing slash.
        variants = {normalized.rstrip("/"), f"{normalized.rstrip('/')}/"}
        for variant in variants:
            record = records_by_url.get(variant)
            if record:
                return record

        raise ValueError(f"MDV product URL was not found in export catalogs: {url}")

    async def _records_by_source_url(self) -> dict[str, MdvCatalogRecord]:
        if self._records_by_url is not None:
            return self._records_by_url
        records: dict[str, MdvCatalogRecord] = {}
        for record in await self.collect_records(include_manuals=False):
            records[self._normalize_url(record.source_url)] = record
        self._records_by_url = records
        return records

    async def _records_by_fallback_key(self) -> dict[str, MdvCatalogRecord]:
        if self._records_by_fallback is not None:
            return self._records_by_fallback
        records: dict[str, MdvCatalogRecord] = {}
        for record in await self.collect_records(include_manuals=False):
            records[self._fallback_key(record.catalog, record.item)] = record
        self._records_by_fallback = records
        return records

    async def _load_catalog(self, catalog: str) -> list[dict[str, Any]]:
        if catalog in self._json_cache:
            return self._json_cache[catalog]
        url = MDV_EXPORT_URLS[catalog]
        async with httpx.AsyncClient(follow_redirects=True, timeout=45.0) as client:
            response = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (Codex MDV Importer)"})
        if response.status_code != 200:
            raise ValueError(f"MDV export {catalog} returned HTTP {response.status_code}")
        data = response.json()
        if not isinstance(data, list):
            raise ValueError(f"MDV export {catalog} has unexpected JSON shape")
        self._json_cache[catalog] = [item for item in data if isinstance(item, dict)]
        return self._json_cache[catalog]

    async def _load_sitemap_urls(self) -> list[str]:
        if self._sitemap_urls is not None:
            return self._sitemap_urls
        async with httpx.AsyncClient(follow_redirects=True, timeout=45.0) as client:
            response = await client.get(MDV_SITEMAP_URL, headers={"User-Agent": "Mozilla/5.0 (Codex MDV Importer)"})
        if response.status_code != 200:
            raise ValueError(f"MDV sitemap returned HTTP {response.status_code}")
        urls = re.findall(r"<loc>(.*?)</loc>", response.text)
        self._sitemap_urls = [html.unescape(url).strip() for url in urls if "/catalog/" in url]
        return self._sitemap_urls

    async def _source_url_for_item(self, catalog: str, item: dict[str, Any]) -> str:
        last_segment_map: dict[str, list[str]] = {}
        for source_url in await self._load_sitemap_urls():
            last = urlsplit(source_url).path.rstrip("/").rsplit("/", 1)[-1].lower()
            if last:
                last_segment_map.setdefault(last, []).append(source_url)

        path_marker = _CATALOG_PATH_MARKERS.get(catalog, "")
        for candidate in self._candidate_slugs(item):
            matches = last_segment_map.get(candidate)
            if not matches:
                continue
            scoped = [url for url in matches if path_marker and path_marker in urlsplit(url).path]
            return self._normalize_url((scoped or matches)[0])

        return self._fallback_url(catalog, item)

    def _candidate_slugs(self, item: dict[str, Any]) -> list[str]:
        props = self._props(item)
        candidates: list[str] = []
        code = str(item.get("CODE") or "").strip()
        if code:
            candidates.append(code)
            candidates.append(code.replace("_", "-"))
        redirect_codes = props.get("REDIRECT_CODES")
        if redirect_codes and str(redirect_codes).lower() != "false":
            candidates.extend(part.strip() for part in str(redirect_codes).split(","))

        indoor = str(props.get("UNIT_INDOOR") or "").strip()
        outdoor = str(props.get("UNIT_OUTDOOR") or "").strip()
        if indoor and outdoor:
            candidates.extend([f"{indoor}-{outdoor}", f"{indoor}/{outdoor}", f"{indoor} {outdoor}"])
        if indoor:
            candidates.extend([indoor, f"{indoor}-"])
        if outdoor:
            candidates.append(outdoor)

        result: list[str] = []
        for candidate in candidates:
            slug = slugify.slugify(candidate)
            if slug and slug not in result:
                result.append(slug)
            if str(candidate).strip().endswith("-") and slug:
                trailing_slug = f"{slug}-"
                if trailing_slug not in result:
                    result.append(trailing_slug)
        return result

    def _build_specs(self, record: MdvCatalogRecord) -> dict[str, Any]:
        item = record.item
        props = self._props(item)
        sections = self._sections(item)
        nonempty = {
            key: value
            for key, value in props.items()
            if value not in (None, "", [], {}, False, "False")
        }
        specs: dict[str, Any] = {
            "brand": "MDV",
            "series": sections.get("SECTION_3") or "",
            "sku": item.get("CODE") or item.get("ID") or "",
            "__mdv_catalog": record.catalog,
            "__mdv_section_1": sections.get("SECTION_1") or "",
            "__mdv_section_2": sections.get("SECTION_2") or "",
            "__mdv_section_3": sections.get("SECTION_3") or "",
            "mdv_rrc_rub": self._price(record.item),
            "__mdv_raw_specs": nonempty,
        }

        specs.update(self._system_type_specs(record))
        self._copy(props, specs, "UNIT_INDOOR", "model_indoor")
        self._copy(props, specs, "UNIT_OUTDOOR", "model_outdoor")
        self._copy(props, specs, "COMPRESSOR_OPER_TYPE", "inverter_type")
        self._copy(props, specs, "COMPRESSOR_TYPE", "compressor_type")
        self._copy(props, specs, "COMPRESSOR_BRAND", "compressor_brand")
        self._copy(props, specs, "POWER_SUPPLY", "power_supply")
        self._copy(props, specs, "POWER_SUPPLY_INDOOR", "power_supply_indoor")
        self._copy(props, specs, "POWER_SUPPLY_OUTDOOR", "power_supply_outdoor")
        self._copy(props, specs, "POWER_CONNECT", "power_supply_location")
        self._copy(props, specs, "COOLING_TYPE", "freon_type")
        self._copy(props, specs, "COOLING_QTY", "Заправка хладагента, кг")
        self._copy(props, specs, "COOLING_ADD", "Дополнительная заправка (г/м)")

        for source, target in _MDV_SIMPLE_SPEC_MAP.items():
            self._copy(props, specs, source, target)

        self._copy_range(props, specs, "NOMINAL_POWER_COOLING_RANGE", "power_cons_cooling_kw", "power_cons_cooling_min_kw", "power_cons_cooling_max_kw")
        self._copy_range(props, specs, "NOMINAL_POWER_HEATING_RANGE", "power_cons_heating_kw", "power_cons_heating_min_kw", "power_cons_heating_max_kw")
        self._copy_range(props, specs, "NOMINAL_CURRENT_COOLING_RANGE", "current_cooling_nominal_a", None, "current_cooling_max_a")
        self._copy_range(props, specs, "NOMINAL_CURRENT_HEATING_RANGE", "current_heating_nominal_a", None, "current_heating_max_a")
        self._copy_temp_range(props, specs, "TEMP_COOLING_LOW", "TEMP_COOLING_MAX", "temp_range_cool")
        self._copy_temp_range(props, specs, "TEMP_HEATING_LOW", "TEMP_HEATING_HIGH", "temp_range_heat")
        self._copy_dimensions(props, specs, "INDOOR", "dimensions_indoor_package_mm")
        self._copy_dimensions(props, specs, "OUTDOOR", "dimensions_outdoor_package_mm")
        return specs

    def _system_type_specs(self, record: MdvCatalogRecord) -> dict[str, Any]:
        sections = self._sections(record.item)
        props = self._props(record.item)
        section_text = " ".join(str(value or "") for value in sections.values())
        indoor_type = self._infer_indoor_type(section_text)
        if record.catalog == "multi" and props.get("UNIT_OUTDOOR") and not props.get("UNIT_INDOOR"):
            return {"type": "наружный блок"}
        if record.catalog == "multi" and props.get("UNIT_INDOOR") and not props.get("UNIT_OUTDOOR"):
            data = {"type": "внутренний блок"}
            if indoor_type:
                data["indoor_type"] = indoor_type
            return data
        if record.catalog == "multi":
            return {"type": "мульти-сплит-система"}
        if record.catalog == "semi":
            data = {"type": "полупромышленный кондиционер"}
            if indoor_type:
                data["indoor_type"] = indoor_type
            return data
        return {"type": "сплит-система", "indoor_type": "настенный"}

    async def _manuals_for_url(self, source_url: str) -> list[dict[str, str]]:
        if not source_url or source_url.startswith("mdv-catalog://"):
            return []
        if source_url in self._manual_cache:
            return self._manual_cache[source_url]
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                response = await client.get(source_url, headers={"User-Agent": "Mozilla/5.0 (Codex MDV Importer)"})
            if response.status_code != 200:
                return []
        except Exception:
            return []
        links = re.findall(r"href=[\"']([^\"']+\.pdf[^\"']*)[\"']", response.text, flags=re.I)
        manuals: list[dict[str, str]] = []
        seen: set[str] = set()
        for idx, link in enumerate(links, start=1):
            url = self._absolute_url(html.unescape(link))
            if not url or url in seen:
                continue
            seen.add(url)
            manuals.append(
                {
                    "kind": "manual",
                    "title": "Инструкция MDV" if idx == 1 else f"Инструкция MDV {idx}",
                    "url": url,
                    "source": "mdv",
                }
            )
        self._manual_cache[source_url] = manuals
        return manuals

    def _title_for_record(self, record: MdvCatalogRecord, specs: dict[str, Any]) -> str:
        props = self._props(record.item)
        series = str(specs.get("series") or "").strip()
        indoor = str(props.get("UNIT_INDOOR") or "").strip()
        outdoor = str(props.get("UNIT_OUTDOOR") or "").strip()
        model = "/".join(part for part in [indoor, outdoor] if part) or str(record.item.get("NAME") or "").strip()
        indoor_type = str(specs.get("indoor_type") or "").strip()
        system_type = str(specs.get("type") or "").strip()

        if system_type == "внутренний блок":
            label = self._inner_block_label(indoor_type)
            return self._join_title([label, "MDV", series, model])
        if system_type == "наружный блок":
            return self._join_title(["Наружный блок", "MDV", series if series != "Наружные блоки" else "", model])
        if system_type == "полупромышленный кондиционер":
            descriptor = self._semi_descriptor(indoor_type)
            return self._join_title([descriptor, "кондиционер", "MDV", series, model])
        return self._join_title(["MDV", series, model])

    def _slug_for_record(self, record: MdvCatalogRecord) -> str:
        source_url = record.source_url
        if source_url and not source_url.startswith("mdv-catalog://"):
            last = urlsplit(source_url).path.rstrip("/").rsplit("/", 1)[-1]
            if last:
                return slugify.slugify(last)
        return slugify.slugify(str(record.item.get("CODE") or record.item.get("NAME") or record.item.get("ID")))

    @staticmethod
    def _props(item: dict[str, Any]) -> dict[str, Any]:
        props = item.get("PROPERTIES")
        return props if isinstance(props, dict) else {}

    @staticmethod
    def _sections(item: dict[str, Any]) -> dict[str, str]:
        sections = item.get("SECTIONS")
        if not isinstance(sections, dict):
            return {}
        return {str(key): str(value or "").strip() for key, value in sections.items()}

    @staticmethod
    def _join_title(parts: list[str]) -> str:
        return re.sub(r"\s+", " ", " ".join(part.strip() for part in parts if part and part.strip())).strip()

    @staticmethod
    def _copy(props: dict[str, Any], specs: dict[str, Any], source: str, target: str) -> None:
        value = props.get(source)
        if value not in (None, "", [], {}, False, "False"):
            specs[target] = value

    def _copy_range(self, props: dict[str, Any], specs: dict[str, Any], source: str, nominal_key: str, min_key: str | None, max_key: str | None) -> None:
        value = str(props.get(source) or "").strip()
        if not value:
            return
        numbers = self._numbers(value)
        if numbers:
            specs[nominal_key] = numbers[0]
        if len(numbers) >= 3:
            if min_key:
                specs[min_key] = numbers[1]
            if max_key:
                specs[max_key] = numbers[2]

    @staticmethod
    def _copy_temp_range(props: dict[str, Any], specs: dict[str, Any], low_key: str, high_key: str, target: str) -> None:
        low = str(props.get(low_key) or "").strip()
        high = str(props.get(high_key) or "").strip()
        if low and high:
            specs[target] = f"от {low} до {high} °C"

    @staticmethod
    def _copy_dimensions(props: dict[str, Any], specs: dict[str, Any], unit: str, target: str) -> None:
        width = str(props.get(f"SIZE_{unit}PACK_WIDTH") or "").strip()
        height = str(props.get(f"SIZE_{unit}PACK_HEIGHT") or "").strip()
        depth = str(props.get(f"SIZE_{unit}PACK_DEPTH") or "").strip()
        if width and height and depth:
            specs[target] = f"{width} × {height} × {depth}"

    @staticmethod
    def _numbers(value: str) -> list[str]:
        return [number.replace(",", ".") for number in re.findall(r"[-+]?\d+(?:[.,]\d+)?", value)]

    def _price(self, item: dict[str, Any]) -> int:
        raw = str(item.get("BASE_PRICE") or "0").replace(" ", "").replace(",", ".")
        try:
            return int(Decimal(raw).quantize(Decimal("1")))
        except (InvalidOperation, ValueError):
            return 0

    def _gallery_urls(self, item: dict[str, Any]) -> list[str]:
        urls: list[str] = []
        detail = self._absolute_url(item.get("DETAIL_PICTURE"))
        if detail:
            urls.append(detail)
        more = str(self._props(item).get("MORE_PHOTO") or "")
        for part in more.split(","):
            url = self._absolute_url(part)
            if url and url not in urls:
                urls.append(url)
        main = self._absolute_url(item.get("PREVIEW_PICTURE"))
        return [url for url in urls if url != main]

    @staticmethod
    def _description(item: dict[str, Any]) -> str:
        values = [item.get("PREVIEW_TEXT"), item.get("DETAIL_TEXT")]
        return "\n\n".join(str(value).strip() for value in values if str(value or "").strip())

    @staticmethod
    def _first_float(value: Any) -> float | None:
        if value is None:
            return None
        match = re.search(r"[-+]?\d+(?:[.,]\d+)?", str(value))
        if not match:
            return None
        try:
            return float(match.group(0).replace(",", "."))
        except ValueError:
            return None

    @staticmethod
    def _absolute_url(value: Any) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        if raw.startswith("//"):
            return f"https:{raw}"
        if raw.startswith("/"):
            return f"{MDV_BASE_URL}{raw}"
        return raw

    @staticmethod
    def _normalize_url(value: str) -> str:
        raw = str(value or "").strip()
        if raw.startswith("mdv-catalog://"):
            return raw
        parts = urlsplit(raw)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))

    @staticmethod
    def _catalog_for_export_url(url: str) -> str | None:
        path = urlsplit(str(url or "").strip()).path.lower()
        if path.endswith("/bytovye-split-sistemy_export.json"):
            return "household"
        if path.endswith("/polupromyshlennye-split-sistemy_export.json"):
            return "semi"
        if path.endswith("/multisplit-sistemy_export.json"):
            return "multi"
        return None

    def _fallback_url(self, catalog: str, item: dict[str, Any]) -> str:
        return f"mdv-catalog://{catalog}/{quote(self._fallback_key(catalog, item))}"

    @staticmethod
    def _fallback_key(catalog: str, item: dict[str, Any]) -> str:
        return f"{catalog}:{item.get('ID') or item.get('CODE') or item.get('NAME')}"

    @staticmethod
    def _fallback_key_from_url(url: str) -> str:
        parts = urlsplit(url)
        return unquote(parts.path.strip("/"))

    def _is_inverter(self, record: MdvCatalogRecord) -> bool:
        text = " ".join(
            [
                str(self._props(record.item).get("COMPRESSOR_OPER_TYPE") or ""),
                str(record.item.get("NAME") or ""),
                " ".join(self._sections(record.item).values()),
            ]
        ).lower()
        if "on/off" in text or "on off" in text or "on-off" in text:
            return False
        return "inverter" in text or "инвертор" in text

    @staticmethod
    def _infer_indoor_type(text: str) -> str:
        normalized = text.lower().replace("ё", "е")
        for marker, value in _INDOOR_TYPE_MARKERS:
            if marker in normalized:
                return value
        return "настенный" if "настенн" in normalized else ""

    @staticmethod
    def _inner_block_label(indoor_type: str) -> str:
        if indoor_type == "кассетный":
            return "Внутренний кассетный блок"
        if indoor_type == "канальный":
            return "Внутренний канальный блок"
        if indoor_type == "напольно-потолочный":
            return "Внутренний напольно-потолочный блок"
        if indoor_type == "колонный":
            return "Внутренний колонный блок"
        return "Внутренний блок"

    @staticmethod
    def _semi_descriptor(indoor_type: str) -> str:
        if indoor_type == "кассетный":
            return "Кассетный"
        if indoor_type == "канальный":
            return "Канальный"
        if indoor_type == "напольно-потолочный":
            return "Напольно-потолочный"
        if indoor_type == "колонный":
            return "Колонный"
        return "Полупромышленный"


_MDV_SIMPLE_SPEC_MAP = {
    "COOLING": "capacity_cooling_kw",
    "COOLING_NOM": "capacity_cooling_kw",
    "COOLING_MIN": "capacity_cooling_min_kw",
    "COOLING_MAX": "capacity_cooling_max_kw",
    "HEATING": "capacity_heating_kw",
    "HEATING_NOM": "capacity_heating_kw",
    "HEATING_MIN": "capacity_heating_min_kw",
    "HEATING_MAX": "capacity_heating_max_kw",
    "NOMINAL_POWER_COOLING": "power_cons_cooling_kw",
    "NOMINAL_POWER_HEATING": "power_cons_heating_kw",
    "NOMINAL_CURRENT_COOLING": "current_cooling_nominal_a",
    "NOMINAL_CURRENT_HEATING": "current_heating_nominal_a",
    "SEER": "seer",
    "SCOP": "scop",
    "SCOP_SIMPLE": "scop",
    "EER": "eer",
    "COP": "cop",
    "CLASS_EE_COOLING": "energy_class_cooling",
    "CLASS_EE_HEATING": "energy_class_heating",
    "AIRFLOW": "airflow_max",
    "AIRFLOW_INDOOR": "airflow_max",
    "AIRFLOW_INDOOR_MAX": "airflow_max",
    "AIRFLOW_OUTDOOR": "airflow_outdoor",
    "NOISE_INDOOR": "noise_indoor",
    "NOISE_OUTDOOR": "noise_outdoor",
    "NOISE_PRESSURE_SIMPLE": "noise_outdoor",
    "PIPE_LENGTH_MAX": "pipe_max_length",
    "VERTICAL_DROP_MAX": "pipe_max_height",
    "PIPE_MAX_ALL_INDOOR": "multi_max_total_pipe_length",
    "PIPE_LIQUID_SIZE_MM": "pipe_liquid",
    "PIPE_LIQUID_SIZE_MM_INCH": "pipe_liquid",
    "PIPE_LIQUID_SIZE_INCH": "pipe_liquid",
    "PIPE_GAZ_SIZE_MM": "pipe_gas",
    "PIPE_GAZ_SIZE_MM_INCH": "pipe_gas",
    "PIPE_GAZ_SIZE_INCH": "pipe_gas",
    "DRAIN_PIPE_OUT_DIAMETER": "drain_pipe_diameter",
    "SIZE_INDOOR_WIDTH": "width_indoor",
    "SIZE_INDOOR_HEIGHT": "height_indoor",
    "SIZE_INDOOR_DEPTH": "depth_indoor",
    "SIZE_OUTDOOR_WIDTH": "width_outdoor",
    "SIZE_OUTDOOR_HEIGHT": "height_outdoor",
    "SIZE_OUTDOOR_DEPTH": "depth_outdoor",
    "WEIGHT_INDOOR_NETTO": "weight_indoor",
    "WEIGHT_INDOOR_BRUTTO": "weight_indoor_package",
    "WEIGHT_OUTDOOR_NETTO": "weight_outdoor",
    "WEIGHT_OUTDOOR_BRUTTO": "weight_outdoor_package",
    "POWER_CABLE_RECOMMEND": "cable_power",
    "CABLE_BETWEEN_UNITS_REC": "cable_interconnect",
    "MAX_INDOOR_CONNECTED": "multi_max_indoor_units",
}


MDV_PROMOTED_PROP_KEYS = set(_MDV_SIMPLE_SPEC_MAP) | {
    "UNIT_INDOOR",
    "UNIT_OUTDOOR",
    "COMPRESSOR_OPER_TYPE",
    "COMPRESSOR_TYPE",
    "COMPRESSOR_BRAND",
    "POWER_SUPPLY",
    "POWER_SUPPLY_INDOOR",
    "POWER_SUPPLY_OUTDOOR",
    "POWER_CONNECT",
    "COOLING_TYPE",
    "COOLING_QTY",
    "COOLING_ADD",
    "NOMINAL_POWER_COOLING_RANGE",
    "NOMINAL_POWER_HEATING_RANGE",
    "NOMINAL_CURRENT_COOLING_RANGE",
    "NOMINAL_CURRENT_HEATING_RANGE",
    "TEMP_COOLING_LOW",
    "TEMP_COOLING_MAX",
    "TEMP_HEATING_LOW",
    "TEMP_HEATING_HIGH",
    "SIZE_INDOORPACK_WIDTH",
    "SIZE_INDOORPACK_HEIGHT",
    "SIZE_INDOORPACK_DEPTH",
    "SIZE_OUTDOORPACK_WIDTH",
    "SIZE_OUTDOORPACK_HEIGHT",
    "SIZE_OUTDOORPACK_DEPTH",
    "MORE_PHOTO",
    "REDIRECT_CODES",
    "ACC_LINK_TO_ELEMENTS",
}
