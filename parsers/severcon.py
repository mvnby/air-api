from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from xml.etree import ElementTree as ET

import httpx
import slugify

from .base import BaseParser


class SeverconEnergoluxParser(BaseParser):
    """Parser for Energolux products from the Severcon YML/XML feed."""

    FEED_URL = "https://www.severcon.ru/bitrix/catalog_export/yandex_187449.php"
    SOURCE_NAME = "severcon"
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "application/xml,text/xml,*/*",
    }
    _EXCLUDED_MARKERS = (
        "аксессуар",
        "инфракрасн",
        "конвектор",
        "нагревател",
        "обогревател",
        "охладител",
        "рекуператор",
        "стойка",
        "штатив",
    )
    _INCLUDED_MARKERS = (
        "блок",
        "кондиционер",
        "система кондиционирования",
        "сплит-система",
        "тепловой насос",
    )

    def __init__(self) -> None:
        self._feed_cache: dict[str, tuple[dict[str, str], dict[str, ET.Element]]] = {}

    def supports(self, url: str) -> bool:
        parts = urlsplit(url.strip())
        return parts.netloc.endswith("severcon.ru") and parts.path.endswith(
            "/bitrix/catalog_export/yandex_187449.php"
        )

    async def get_import_urls(self, url: str) -> List[str]:
        """Expand the feed URL into stable per-offer pseudo-URLs."""
        normalized_url = self._feed_url_without_offer(url)
        if self._offer_id_from_url(url):
            return [url]

        categories, offers = await self._load_feed(normalized_url)
        urls: List[str] = []
        for offer_id, offer in offers.items():
            if self._is_importable_offer(offer, categories):
                urls.append(self._offer_url(normalized_url, offer_id))
        return urls

    async def parse(self, url: str) -> Dict[str, Any]:
        feed_url = self._feed_url_without_offer(url)
        offer_id = self._offer_id_from_url(url)
        categories, offers = await self._load_feed(feed_url)

        if not offer_id:
            eligible = [
                oid for oid, offer in offers.items() if self._is_importable_offer(offer, categories)
            ]
            if not eligible:
                raise ValueError("Severcon feed does not contain importable Energolux offers.")
            offer_id = eligible[0]

        offer = offers.get(offer_id)
        if offer is None:
            raise ValueError(f"Severcon offer #{offer_id} was not found in the feed.")
        if not self._is_importable_offer(offer, categories):
            raise ValueError(f"Severcon offer #{offer_id} is not an importable Energolux HVAC item.")

        name = self._text(offer, "name") or "Energolux"
        offer_url = self._text(offer, "url")
        category = categories.get(self._text(offer, "categoryId"), "")
        params = self._params(offer)
        specs = self._specs(offer=offer, params=params, category=category, offer_id=offer_id)
        metrics = self._metrics(specs=specs, title=name, category=category)
        pictures = self._pictures(offer=offer, params=params)
        article = specs.get("Артикул") or offer_id
        title = self._display_title(raw_title=name, specs=specs, category=category)

        return {
            "title": title,
            "slug": self._slug(offer_url=offer_url, title=name, article=article),
            "description": self._clean_text(self._text(offer, "description")),
            "price": int(self._price(offer)),
            "price_currency": (self._text(offer, "currencyId") or "RUB").upper(),
            "area": metrics["area"],
            "main_image": pictures[0] if pictures else "",
            "images": pictures[1:] if len(pictures) > 1 else [],
            "save_gallery": True,
            "categories": [],
            "specs": specs,
            "metrics": metrics,
            "related_urls": [],
            "availability": "В наличии",
            "in_stock": True,
            "refresh_title_on_update": True,
        }

    async def _load_feed(self, feed_url: str) -> tuple[dict[str, str], dict[str, ET.Element]]:
        if feed_url in self._feed_cache:
            return self._feed_cache[feed_url]

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=30.0,
            headers=self._HEADERS,
        ) as client:
            response = await client.get(feed_url)
            if response.status_code != 200:
                raise Exception(f"Ошибка загрузки XML Severcon: {response.status_code}")

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise ValueError("Severcon XML feed could not be parsed.") from exc

        shop = root.find("shop")
        if shop is None:
            raise ValueError("Severcon XML feed does not contain shop node.")

        categories = {
            str(category.attrib.get("id", "")).strip(): self._clean_text("".join(category.itertext()))
            for category in shop.findall("./categories/category")
        }
        offers = {
            str(offer.attrib.get("id", "")).strip(): offer
            for offer in shop.findall("./offers/offer")
            if str(offer.attrib.get("id", "")).strip()
        }
        self._feed_cache[feed_url] = (categories, offers)
        return categories, offers

    @classmethod
    def _feed_url_without_offer(cls, url: str) -> str:
        parts = urlsplit(url.strip())
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))

    @classmethod
    def _offer_id_from_url(cls, url: str) -> str:
        parts = urlsplit(url.strip())
        fragment_params = parse_qs(parts.fragment)
        query_params = parse_qs(parts.query)
        for params in (fragment_params, query_params):
            for key in ("offer", "offer_id", "id"):
                value = params.get(key)
                if value and value[0]:
                    return value[0].strip()
        return ""

    @classmethod
    def _offer_url(cls, feed_url: str, offer_id: str) -> str:
        parts = urlsplit(feed_url)
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, "", urlencode({"offer": offer_id}))
        )

    @staticmethod
    def _text(parent: ET.Element, tag: str) -> str:
        child = parent.find(tag)
        if child is None:
            return ""
        return SeverconEnergoluxParser._clean_text("".join(child.itertext()))

    @staticmethod
    def _clean_text(value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()

    @classmethod
    def _params(cls, offer: ET.Element) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for param in offer.findall("param"):
            key = cls._clean_text(param.attrib.get("name", "")).rstrip(":")
            value = cls._clean_text("".join(param.itertext()))
            if not key or not value:
                continue
            if key not in result:
                result[key] = value
        return result

    @classmethod
    def _price(cls, offer: ET.Element) -> Decimal:
        raw = cls._text(offer, "price").replace(" ", "").replace(",", ".")
        try:
            return Decimal(raw)
        except (InvalidOperation, ValueError):
            return Decimal("0")

    @classmethod
    def _is_importable_offer(cls, offer: ET.Element, categories: dict[str, str]) -> bool:
        vendor = cls._text(offer, "vendor")
        name = cls._text(offer, "name")
        category = categories.get(cls._text(offer, "categoryId"), "")
        combined = f"{vendor} {name} {category}".lower().replace("ё", "е")
        if "energolux" not in combined:
            return False
        if cls._price(offer) <= Decimal("1"):
            return False
        if any(marker in combined for marker in cls._EXCLUDED_MARKERS):
            return False
        return any(marker in combined for marker in cls._INCLUDED_MARKERS)

    @classmethod
    def _specs(
        cls,
        *,
        offer: ET.Element,
        params: Dict[str, str],
        category: str,
        offer_id: str,
    ) -> Dict[str, Any]:
        specs: Dict[str, Any] = {
            key: value
            for key, value in params.items()
            if key not in {"Доп. фото", "Цена по запросу"}
        }
        specs.setdefault("Бренд", cls._text(offer, "vendor") or "Energolux")
        specs.setdefault("Артикул", params.get("Артикул") or offer_id)
        cls._reconcile_models_from_article(specs)
        specs["Категория поставщика"] = category
        specs["ID предложения Severcon"] = offer_id
        source_url = cls._text(offer, "url")
        if source_url:
            specs["URL поставщика"] = source_url
        warranty = cls._text(offer, "manufacturer_warranty")
        if warranty:
            specs.setdefault("Гарантия", warranty)

        inferred_type = cls._infer_type(title=cls._text(offer, "name"), category=category)
        if inferred_type:
            specs.setdefault("Тип", inferred_type)
        indoor_type = cls._infer_indoor_type(title=cls._text(offer, "name"), category=category)
        if indoor_type:
            specs.setdefault("Тип внутреннего блока", indoor_type)
        series = cls._series_from_category(category)
        if series:
            specs.setdefault("Серия", series)
        inverter_type = cls._infer_inverter_type(
            title=cls._text(offer, "name"),
            category=category,
            current=specs.get("Тип управления компрессором"),
        )
        if inverter_type:
            specs.setdefault("Тип управления компрессором", inverter_type)
        return specs

    @classmethod
    def _reconcile_models_from_article(cls, specs: Dict[str, Any]) -> None:
        article = cls._clean_text(str(specs.get("Артикул") or ""))
        if "/" not in article:
            return
        parts = [cls._clean_text(part) for part in article.split("/") if cls._clean_text(part)]
        if len(parts) < 2:
            return
        specs["Модель внутреннего блока"] = parts[0]
        specs["Модель наружного блока"] = parts[1]

    @classmethod
    def _pictures(cls, *, offer: ET.Element, params: Dict[str, str]) -> List[str]:
        urls: List[str] = []
        for picture in offer.findall("picture"):
            value = cls._clean_text("".join(picture.itertext()))
            if value and value not in urls:
                urls.append(value)
        for value in re.split(r"\s*,\s*", params.get("Доп. фото", "")):
            if value and value not in urls:
                urls.append(value)
        return urls

    @classmethod
    def _slug(cls, *, offer_url: str, title: str, article: str) -> str:
        if offer_url:
            path = urlsplit(offer_url).path.rstrip("/")
            last = path.rsplit("/", 1)[-1]
            if last.endswith(".html"):
                last = last[:-5]
            if last:
                return slugify.slugify(last)
        return slugify.slugify(f"energolux-{article or title}")

    @classmethod
    def _metrics(cls, *, specs: Dict[str, Any], title: str, category: str = "") -> Dict[str, Any]:
        cooling_kw = cls._parse_first_number(str(specs.get("Холодопроизводительность") or ""))
        area = int(round(cooling_kw * 10)) if cooling_kw else 0
        combined = " ".join(
            [
                str(specs.get("Тип управления компрессором") or ""),
                title,
                category,
            ]
        ).lower().replace("ё", "е")
        combined = combined.replace("—", "-")
        is_inverter = False
        if cls._has_on_off_marker(combined):
            is_inverter = False
        elif "инвертор" in combined or "inverter" in combined:
            is_inverter = True
        return {
            "area": area,
            "is_inverter": is_inverter,
            "power_cooling": cooling_kw,
        }

    @staticmethod
    def _parse_first_number(value: str) -> float | None:
        if not value:
            return None
        match = re.search(r"(-?\d[\d\s]*(?:[.,]\d+)?)", value.replace("\xa0", " "))
        if not match:
            return None
        try:
            return float(match.group(1).replace(" ", "").replace(",", "."))
        except ValueError:
            return None

    @classmethod
    def _infer_type(cls, *, title: str, category: str) -> str:
        combined = f"{title} {category}".lower().replace("ё", "е")
        if "наружн" in combined and "блок" in combined:
            return "наружный блок"
        if "внутренн" in combined and "блок" in combined:
            return "внутренний блок"
        if "блок" in combined and any(
            marker in combined
            for marker in ("настенн", "кассет", "каналь", "напольно", "потолоч", "колонн")
        ):
            return "внутренний блок"
        if "мульти" in combined or "multi" in combined:
            return "мульти-сплит-система"
        if "сплит" in combined:
            return "сплит-система"
        if "тепловой насос" in combined or "система кондиционирования" in combined:
            return "сплит-система"
        return ""

    @classmethod
    def _infer_indoor_type(cls, *, title: str, category: str) -> str:
        combined = f"{title} {category}".lower().replace("ё", "е")
        if "кассет" in combined:
            return "кассетный"
        if "каналь" in combined:
            return "канальный"
        if "напольно" in combined or "потолоч" in combined:
            return "напольно-потолочный"
        if "колонн" in combined:
            return "колонный"
        if "настенн" in combined:
            return "настенный"
        return ""

    @classmethod
    def _infer_inverter_type(cls, *, title: str, category: str, current: Any = None) -> str:
        combined = f"{current or ''} {title} {category}".lower().replace("ё", "е")
        combined = combined.replace("—", "-")
        if cls._has_on_off_marker(combined) or "классическ" in combined:
            return "On/Off"
        if "инвертор" in combined or "inverter" in combined:
            return "Инверторный"
        return ""

    @staticmethod
    def _has_on_off_marker(text: str) -> bool:
        normalized = text.lower().replace("ё", "е").replace("—", "-")
        return bool(
            "неинвертор" in normalized
            or "on/off" in normalized
            or "on-off" in normalized
            or "on off" in normalized
            or "onoff" in normalized
        )

    @classmethod
    def _series_from_category(cls, category: str) -> str:
        text = cls._clean_text(category)
        if not text:
            return ""

        series_match = re.search(r"\bсер(?:ия|ии)\s+(.+)$", text, flags=re.IGNORECASE)
        if series_match:
            return cls._clean_series(series_match.group(1))

        brand_match = re.search(r"energolux\s+(.+)$", text, flags=re.IGNORECASE)
        if not brand_match:
            return ""

        candidate = brand_match.group(1)
        return cls._clean_series(candidate)

    @classmethod
    def _clean_series(cls, value: str) -> str:
        text = cls._clean_text(value)
        text = re.sub(r"\bсер(?:ия|ии)\b", "", text, flags=re.IGNORECASE)
        text = cls._clean_text(text.strip(" -/"))
        generic = {
            "настенный блок",
            "настенные блоки",
            "наружный блок",
            "наружные блоки",
            "канальные блоки",
            "кассетные блоки",
            "сплит-системы",
        }
        if text.lower().replace("ё", "е") in generic:
            return ""
        return text

    @classmethod
    def _display_title(cls, *, raw_title: str, specs: Dict[str, Any], category: str) -> str:
        brand = cls._clean_text(str(specs.get("Бренд") or "Energolux"))
        series = cls._clean_text(str(specs.get("Серия") or ""))
        product_type = str(specs.get("Тип") or "")
        indoor_type = str(specs.get("Тип внутреннего блока") or "")
        model = cls._model_label(specs=specs, raw_title=raw_title, brand=brand, series=series)

        if product_type == "внутренний блок":
            prefix = cls._inner_block_title(indoor_type)
            return cls._join_title_parts([prefix, brand, series, model])

        if product_type == "наружный блок":
            fallback_series = "" if series else cls._series_from_title(raw_title)
            return cls._join_title_parts(["Наружный блок", brand, series or fallback_series, model])

        descriptor = cls._semi_industrial_descriptor(indoor_type=indoor_type, title=raw_title, category=category)
        if descriptor:
            return cls._join_title_parts([descriptor, "кондиционер", brand, series, model])

        if product_type == "сплит-система":
            return cls._join_title_parts([brand, series, model]) or cls._clean_source_title(raw_title)

        if product_type == "мульти-сплит-система":
            return cls._join_title_parts(["Мульти-сплит-система", brand, series, model])

        cleaned = cls._clean_source_title(raw_title)
        if cleaned.lower().startswith(brand.lower()):
            return cleaned
        brand_pos = cleaned.lower().find(brand.lower())
        if brand_pos >= 0:
            return cls._clean_text(cleaned[brand_pos:])
        return cls._join_title_parts([brand, series, model]) or cleaned

    @classmethod
    def _model_label(
        cls,
        *,
        specs: Dict[str, Any],
        raw_title: str,
        brand: str,
        series: str,
    ) -> str:
        article = cls._clean_text(str(specs.get("Артикул") or ""))
        if "/" in article and not article.isdigit():
            return article.replace(" / ", "/").replace(" /", "/").replace("/ ", "/")

        indoor = cls._clean_text(str(specs.get("Модель внутреннего блока") or ""))
        outdoor = cls._clean_text(str(specs.get("Модель наружного блока") or ""))
        if indoor and outdoor:
            return f"{indoor}/{outdoor}"
        if indoor:
            return indoor
        if outdoor:
            return outdoor

        for key in ("Модель", "Артикул"):
            value = cls._clean_text(str(specs.get(key) or ""))
            if value and not value.isdigit():
                return value

        cleaned = cls._clean_source_title(raw_title)
        tail = cleaned
        for marker in (brand, series):
            if not marker:
                continue
            match = re.search(re.escape(marker), tail, flags=re.IGNORECASE)
            if match:
                tail = tail[match.end() :]
        return cls._clean_text(tail.strip(" -/"))

    @classmethod
    def _clean_source_title(cls, title: str) -> str:
        text = cls._clean_text(title)
        text = re.sub(
            r"^(?:инверторная|классическая)?\s*система\s+кондиционирования\s+",
            "",
            text,
            flags=re.IGNORECASE,
        )
        return cls._clean_text(text)

    @classmethod
    def _series_from_title(cls, title: str) -> str:
        cleaned = cls._clean_source_title(title)
        match = re.search(r"Energolux\s+(.+?)\s+[A-ZА-Я]{2,}[\wА-Яа-я/-]*", cleaned)
        if not match:
            return ""
        candidate = cls._clean_series(match.group(1))
        if candidate.lower().replace("ё", "е") in {"smart multi", "big multi"}:
            return candidate
        return ""

    @staticmethod
    def _join_title_parts(parts: List[str]) -> str:
        return SeverconEnergoluxParser._clean_text(" ".join(str(part or "").strip() for part in parts if part))

    @classmethod
    def _semi_industrial_descriptor(cls, *, indoor_type: str, title: str, category: str) -> str:
        combined = f"{indoor_type} {title} {category}".lower().replace("ё", "е")
        if "кассет" in combined:
            return "Кассетный"
        if "каналь" in combined:
            return "Канальный"
        if "напольно" in combined or "потолоч" in combined:
            return "Напольно-потолочный"
        if "колон" in combined:
            return "Колонный"
        return ""

    @classmethod
    def _inner_block_title(cls, indoor_type: str) -> str:
        normalized = indoor_type.lower().replace("ё", "е")
        if "кассет" in normalized:
            return "Внутренний кассетный блок"
        if "каналь" in normalized:
            return "Внутренний канальный блок"
        if "напольно" in normalized or "потолоч" in normalized:
            return "Внутренний напольно-потолочный блок"
        if "колон" in normalized:
            return "Внутренний колонный блок"
        return "Внутренний блок"
