from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag
import httpx
from slugify import slugify

from .base import BaseParser


HISENSE_SUPPORTED_HOSTS = ("hisense-air.ru", "breez.ru")


class HisenseCatalogParser(BaseParser):
    SOURCE_NAME = "hisense"

    def supports(self, url: str) -> bool:
        parts = urlsplit(str(url or "").strip())
        host = parts.netloc.lower()
        if not any(host == item or host.endswith(f".{item}") for item in HISENSE_SUPPORTED_HOSTS):
            return False
        return parts.path.startswith("/product/") or parts.path.startswith("/products/")

    async def get_import_urls(self, url: str) -> list[str]:
        page = await self._fetch_page(url)
        models = self._extract_models(page.soup)
        if not models:
            return [self._canonical_page_url(page.url)]
        return [self._with_model_fragment(page.url, model) for model in models]

    async def parse(self, url: str) -> dict[str, Any]:
        selected_model = self._model_from_url(url)
        page = await self._fetch_page(url)
        models = self._extract_models(page.soup)
        if selected_model is None:
            if len(models) == 1:
                selected_model = models[0]
            elif len(models) > 1:
                raise ValueError("Hisense series URL contains multiple models; use model fragment or bulk import")

        model_specs = self._extract_model_specs(page.soup, selected_model)
        model = selected_model or str(model_specs.get("Модель") or model_specs.get("model") or "").strip()
        if not model:
            raise ValueError("Hisense model was not found on the page")

        images = self._extract_images(page.soup, page.url)
        description = self._build_description(page.soup)
        series_title = str(model_specs.get("Серия") or self._page_title(page.soup) or "").strip()
        specs = self._augment_specs(model_specs, model=model, series_title=series_title, source_url=page.url)
        catalog = str(specs.get("__hisense_catalog") or "")
        cooling_kw = self._first_float(
            specs.get("capacity_cooling_kw")
            or specs.get("Холодопроизводительность (кВт)")
            or specs.get("Холодопроизводительность")
        )
        area = self._first_int(specs.get("area_m2") or specs.get("Эффективен для помещений площадью до, м 2"))

        return {
            "title": self._title_for_model(model),
            "slug": slugify(f"hisense-{model}", lowercase=True),
            "description": description,
            "price": 0,
            "area": area or (int(round(cooling_kw * 10)) if cooling_kw else 0),
            "main_image": images[0] if images else "",
            "images": images,
            "save_gallery": True,
            "require_media_download": True,
            "categories": [],
            "specs": specs,
            "metrics": {
                "area": area or (int(round(cooling_kw * 10)) if cooling_kw else 0),
                "is_inverter": self._is_inverter(specs),
                "power_cooling": cooling_kw,
            },
            "related_urls": [self._with_model_fragment(page.url, item) for item in models if item != model],
            "availability": "Каталог Hisense",
            "in_stock": True,
            "refresh_title_on_update": True,
            "publish_on_update": True,
            "source_url": self._with_model_fragment(page.url, model),
            "manuals": self._extract_manuals(page.soup, page.url),
        }

    async def parse_series_content(self, url: str) -> dict[str, Any]:
        page = await self._fetch_page(url)
        images = self._extract_images(page.soup, page.url)
        return {
            "title": self._page_title(page.soup),
            "description": self._build_description(page.soup),
            "source_url": self._canonical_page_url(page.url),
            "hero_image": images[0] if images else None,
            "gallery_images": images[:12],
            "features": self._extract_short_features(page.soup),
        }

    async def _fetch_page(self, url: str) -> "_FetchedPage":
        page_url = self._canonical_page_url(url)
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=25.0,
            headers={"User-Agent": "Mozilla/5.0 (Codex Hisense Importer)"},
            verify=False,
        ) as client:
            response = await client.get(page_url)
            response.raise_for_status()
            return _FetchedPage(url=str(response.url), soup=BeautifulSoup(response.text, "html.parser"))

    @staticmethod
    def _canonical_page_url(url: str) -> str:
        parts = urlsplit(str(url or "").strip())
        return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, "")).rstrip("/")

    @staticmethod
    def _model_from_url(url: str) -> str | None:
        fragment = urlsplit(str(url or "")).fragment
        if not fragment:
            return None
        parsed = parse_qs(fragment)
        model = (parsed.get("model") or [""])[0]
        return unquote(model).strip() or None

    @staticmethod
    def _with_model_fragment(url: str, model: str) -> str:
        parts = urlsplit(HisenseCatalogParser._canonical_page_url(url))
        fragment = f"model={quote(model.strip(), safe='')}"
        return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, fragment))

    @staticmethod
    def _extract_models(soup: BeautifulSoup) -> list[str]:
        models: list[str] = []
        seen: set[str] = set()
        for table in soup.select("table.techtable"):
            rows = HisenseCatalogParser._table_rows(table)
            if not rows or len(rows[0]) < 2:
                continue
            for value in rows[0][1:]:
                model = HisenseCatalogParser._clean_text(value)
                if not HisenseCatalogParser._looks_like_model(model) or model in seen:
                    continue
                seen.add(model)
                models.append(model)
        return models

    @staticmethod
    def _extract_model_specs(soup: BeautifulSoup, selected_model: str | None) -> dict[str, str]:
        specs: dict[str, str] = {}
        selected_norm = HisenseCatalogParser._normalize_model_token(selected_model or "")
        for table in soup.select("table.techtable"):
            rows = HisenseCatalogParser._table_rows(table)
            if not rows or len(rows[0]) < 2:
                continue
            headers = [HisenseCatalogParser._normalize_model_token(item) for item in rows[0]]
            model_idx = -1
            if selected_norm:
                for idx, header in enumerate(headers):
                    if header == selected_norm:
                        model_idx = idx
                        break
            if model_idx < 1:
                continue

            for row in rows[1:]:
                if len(row) <= model_idx:
                    continue
                key = HisenseCatalogParser._clean_text(row[0])
                value = HisenseCatalogParser._clean_text(row[model_idx])
                if not key or not value or value == "-":
                    continue
                if key not in specs:
                    specs[key] = value
        return specs

    @staticmethod
    def _table_rows(table: Tag) -> list[list[str]]:
        rows: list[list[str]] = []
        for row in table.select("tr"):
            cells = [HisenseCatalogParser._clean_text(cell.get_text(" ", strip=True)) for cell in row.select("th,td")]
            if any(cells):
                rows.append(cells)
        return rows

    @staticmethod
    def _augment_specs(raw_specs: dict[str, str], *, model: str, series_title: str, source_url: str) -> dict[str, Any]:
        specs: dict[str, Any] = dict(raw_specs)
        specs.setdefault("brand", "Hisense")
        specs.setdefault("Бренд", "Hisense")
        specs.setdefault("model", model)
        specs.setdefault("Модель", model)
        if series_title:
            specs.setdefault("series", series_title)
            specs.setdefault("Серия", series_title)

        indoor_model = specs.get("Модель внутреннего блока")
        outdoor_model = specs.get("Модель наружного блока")
        if indoor_model:
            specs.setdefault("model_indoor", indoor_model)
        if outdoor_model:
            specs.setdefault("model_outdoor", outdoor_model)

        indoor_type = HisenseCatalogParser._normalize_indoor_type(specs.get("Тип внутреннего блока"))
        if indoor_type:
            specs["indoor_type"] = indoor_type

        catalog = HisenseCatalogParser._infer_catalog(source_url, model=model, specs=specs)
        specs["__hisense_catalog"] = catalog
        specs["type"] = HisenseCatalogParser._type_for_catalog(catalog, specs=specs)

        cooling = specs.get("Холодопроизводительность (кВт)") or specs.get("Холодопроизводительность")
        heating = specs.get("Теплопроизводительность (кВт)") or specs.get("Теплопроизводительность")
        if cooling:
            specs.setdefault("capacity_cooling_kw", cooling)
        if heating:
            specs.setdefault("capacity_heating_kw", heating)

        area = specs.get("Эффективен для помещений площадью до, м 2") or specs.get(
            "Эффективен для помещений площадью до м 2"
        )
        if area:
            specs.setdefault("area_m2", area)

        wifi = specs.get("Управление c мобильного приложения по Wi-Fi") or specs.get(
            "Управление с мобильного приложения по Wi-Fi"
        )
        if wifi:
            specs.setdefault("wifi_ready", wifi)
        return specs

    @staticmethod
    def _infer_catalog(source_url: str, *, model: str, specs: dict[str, Any]) -> str:
        text = " ".join(
            str(value or "")
            for value in (
                source_url,
                model,
                specs.get("type"),
                specs.get("Серия"),
                specs.get("Тип внутреннего блока"),
                specs.get("Модель внутреннего блока"),
                specs.get("Модель наружного блока"),
            )
        ).casefold()
        if "mob-cond" in text or "мобиль" in text:
            return "household"
        if "multi" in text or "мульти" in text or model.upper().startswith(("AMW", "AMS", "AKT")):
            return "multi"
        if any(marker in text for marker in ("кассет", "каналь", "напольно", "потолоч", "колон", "консол")):
            return "semi"
        return "household"

    @staticmethod
    def _type_for_catalog(catalog: str, *, specs: dict[str, Any]) -> str:
        if catalog == "multi":
            if specs.get("Модель наружного блока") and not specs.get("Модель внутреннего блока"):
                return "наружный блок"
            return "внутренний блок"
        if catalog == "semi":
            return "полупромышленный кондиционер"
        if "мобиль" in str(specs.get("Серия") or "").casefold():
            return "мобильный кондиционер"
        return "сплит-система"

    @staticmethod
    def _normalize_indoor_type(value: Any) -> str | None:
        text = str(value or "").casefold().replace("ё", "е")
        if "кассет" in text:
            return "кассетный"
        if "каналь" in text:
            return "канальный"
        if "напольно" in text or "потолоч" in text:
            return "напольно-потолочный"
        if "колон" in text:
            return "колонный"
        if "консол" in text:
            return "напольно-потолочный"
        if "настенн" in text:
            return "настенный"
        return None

    @staticmethod
    def _extract_images(soup: BeautifulSoup, current_url: str) -> list[str]:
        images: list[str] = []
        seen: set[str] = set()
        for img in soup.select("img"):
            raw = img.get("data-src") or img.get("data-lazy-src") or img.get("src") or ""
            url = HisenseCatalogParser._absolute_url(str(raw), current_url)
            if not url or "/catalog/hisense/" not in url:
                continue
            if url in seen:
                continue
            seen.add(url)
            images.append(url)
        return images

    @staticmethod
    def _extract_manuals(soup: BeautifulSoup, current_url: str) -> list[dict[str, str]]:
        manuals: list[dict[str, str]] = []
        seen: set[str] = set()
        for link in soup.select("a[href]"):
            href = str(link.get("href") or "")
            if ".pdf" not in href.casefold():
                continue
            url = HisenseCatalogParser._absolute_url(href, current_url)
            if not url or url in seen:
                continue
            seen.add(url)
            title = HisenseCatalogParser._clean_text(link.get_text(" ", strip=True)) or "Инструкция"
            manuals.append({"kind": "manual", "title": title, "url": url, "source": "hisense"})
        return manuals

    @staticmethod
    def _build_description(soup: BeautifulSoup) -> str:
        chunks: list[str] = []
        for selector in (".small-desc", ".full-desc", ".article-list"):
            node = soup.select_one(selector)
            if not node:
                continue
            text = HisenseCatalogParser._clean_text(node.get_text(" ", strip=True))
            if text and text not in chunks:
                chunks.append(text)
        return "\n\n".join(chunks)

    @staticmethod
    def _extract_short_features(soup: BeautifulSoup) -> list[str]:
        features: list[str] = []
        seen: set[str] = set()
        for item in soup.select(".article-list li"):
            text = HisenseCatalogParser._clean_text(item.get_text(" ", strip=True))
            if not text or text.casefold() in seen:
                continue
            seen.add(text.casefold())
            features.append(text)
        return features[:12]

    @staticmethod
    def _page_title(soup: BeautifulSoup) -> str:
        node = soup.select_one(".product-full-title") or soup.select_one("h1")
        return HisenseCatalogParser._clean_text(node.get_text(" ", strip=True)) if node else ""

    @staticmethod
    def _title_for_model(model: str) -> str:
        return f"Hisense {model.strip()}"

    @staticmethod
    def _absolute_url(raw: str, current_url: str) -> str:
        value = str(raw or "").strip()
        if not value or value.startswith("data:"):
            return ""
        if value.startswith("//"):
            return f"https:{value}"
        return urljoin(current_url, value)

    @staticmethod
    def _clean_text(value: Any) -> str:
        text = str(value or "").replace("\xa0", " ")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def _normalize_model_token(value: str) -> str:
        return re.sub(r"\s+", "", str(value or "").strip().upper())

    @staticmethod
    def _looks_like_model(value: str) -> bool:
        text = value.strip()
        return bool(re.search(r"[A-Za-zА-Яа-я]", text) and re.search(r"\d", text) and len(text) >= 4)

    @staticmethod
    def _first_float(value: Any) -> float | None:
        numbers = re.findall(r"[-+]?\d+(?:[.,]\d+)?", str(value or ""))
        if not numbers:
            return None
        if len(numbers) >= 3 and "/" in str(value):
            raw = numbers[1]
        else:
            raw = numbers[0]
        try:
            number = float(raw.replace(",", "."))
        except ValueError:
            return None
        return number / 1000 if abs(number) >= 100 else number

    @staticmethod
    def _first_int(value: Any) -> int | None:
        number = HisenseCatalogParser._first_float(value)
        return int(round(number)) if number is not None else None

    @staticmethod
    def _is_inverter(specs: dict[str, Any]) -> bool:
        text = " ".join(str(specs.get(key) or "") for key in ("Инверторная технология", "inverter", "Серия"))
        lowered = text.casefold()
        if "нет" in lowered:
            return False
        return any(marker in lowered for marker in ("да", "inverter", "инвертор"))


class _FetchedPage:
    def __init__(self, *, url: str, soup: BeautifulSoup) -> None:
        self.url = url
        self.soup = soup
