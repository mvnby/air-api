import re
from typing import Any, Dict, List
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from .base import BaseParser


class Lg24Parser(BaseParser):
    """Parser for lg24.by product pages (WooCommerce)."""

    BASE_URL = "https://lg24.by"
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    }
    _DOC_SPEC_KEY_MARKERS = (
        "руководство",
        "инструкция",
        "manual",
        "user guide",
        "паспорт",
    )
    _KNOWN_SERIES = (
        "ARTCOOL Gallery Special",
        "ARTCOOL Gallery Premium",
        "DUALCOOL Premium",
        "ARTCOOL Gallery",
        "ARTCOOL Mirror",
        "Ultra Inverter R32",
        "Ultra Inverter",
        "Smart Inverter",
        "Deluxe Pro",
        "EVO Max",
        "ECO Smart",
        "LOOK Smart",
        "Smart Line",
        "Objet Green",
        "Objet Beige",
        "PuriCare",
        "PROCOOL",
        "EVOCOOL",
        "ECO",
    )
    _CATEGORY_STOP_PARTS = {
        "главная",
        "каталог",
        "кондиционеры для дома",
        "коммерческие кондиционеры",
        "настенный блок",
        "канальный блок",
        "кассетный блок",
        "потолочный блок",
        "напольно-потолочный блок",
        "колонный блок",
    }

    def supports(self, url: str) -> bool:
        parts = urlsplit(str(url or ""))
        if "lg24.by" not in parts.netloc:
            return False
        return parts.path.startswith("/product/") or parts.path.startswith("/product-category/")

    @staticmethod
    def _is_category_url(url: str) -> bool:
        return urlsplit(str(url or "")).path.startswith("/product-category/")

    @staticmethod
    def _is_product_url(url: str) -> bool:
        return urlsplit(str(url or "")).path.startswith("/product/")

    async def get_import_urls(self, url: str) -> List[str]:
        if not self._is_category_url(url):
            return [url.strip()]

        product_urls: List[str] = []
        seen_products: set[str] = set()
        seen_pages: set[str] = set()
        pending_pages: List[str] = [url.strip()]

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=20.0,
            headers=self._HEADERS,
        ) as client:
            while pending_pages and len(seen_pages) < 20:
                page_url = pending_pages.pop(0)
                if page_url in seen_pages:
                    continue
                seen_pages.add(page_url)

                response = await client.get(page_url)
                if response.status_code != 200:
                    raise Exception(f"Ошибка загрузки категории lg24.by: {response.status_code}")

                soup = BeautifulSoup(response.text, "html.parser")
                for link in soup.select("li.product a[href*='/product/'], a.woocommerce-LoopProduct-link[href]"):
                    href = self._to_abs_url(link.get("href", ""), str(response.url)).split("#")[0]
                    if not href or not self._is_product_url(href):
                        continue
                    normalized = href.rstrip("/") + "/"
                    if normalized in seen_products:
                        continue
                    seen_products.add(normalized)
                    product_urls.append(normalized)

                for link in soup.select(".woocommerce-pagination a[href], a.page-numbers[href]"):
                    href = self._to_abs_url(link.get("href", ""), str(response.url)).split("#")[0]
                    if href and href not in seen_pages and href not in pending_pages:
                        pending_pages.append(href)

        return product_urls or [url.strip()]

    @staticmethod
    def _slug_from_url(url: str) -> str:
        path = url.rstrip("/").split("?")[0]
        segments = [segment for segment in path.split("/") if segment]
        return segments[-1] if segments else "unknown"

    @staticmethod
    def _ensure_brand_prefix(title: str, brand: str = "LG") -> str:
        normalized = re.sub(r"\s+", " ", (title or "").strip())
        if not normalized:
            return brand
        if re.search(rf"\b{re.escape(brand)}\b", normalized, flags=re.IGNORECASE):
            return normalized
        return f"{brand} {normalized}".strip()

    @staticmethod
    def _normalize_model_title(raw_title: str) -> str:
        title = re.sub(r"\s+", " ", (raw_title or "").strip())
        if not title:
            return "Без названия"

        # Remove leading descriptor adjectives to expose core product noun.
        title = re.sub(
            r"^(?:(?:кассетн(?:ый|ая|ое|ые)|настенн(?:ый|ая|ое|ые)|канальн(?:ый|ая|ое|ые)|"
            r"напольно-потолочн(?:ый|ая|ое|ые)|мобильн(?:ый|ая|ое|ые)|бытов(?:ой|ая|ое|ые)|"
            r"потолочн(?:ый|ая|ое|ые)|средненапорн(?:ый|ая|ое|ые)|низконапорн(?:ый|ая|ое|ые)|"
            r"высоконапорн(?:ый|ая|ое|ые)|\d+[-\s]?поточн(?:ый|ая|ое|ые)|"
            r"колонн(?:ый|ая|ое|ые)|универсальн(?:ый|ая|ое|ые)|инверторн(?:ый|ая|ое|ые)|"
            r"полупромышленн(?:ый|ая|ое|ые))\s+)+",
            "",
            title,
            flags=re.IGNORECASE,
        )

        # Keep model-oriented title in DB (without generic product type noun).
        title = re.sub(
            r"^(?:тип|кондиционер|сплит[\s-]?система|мульти[\s-]?сплит[\s-]?система|внутренний\s+блок|наружный\s+блок)\s+",
            "",
            title,
            flags=re.IGNORECASE,
        )
        title = re.sub(r"\s+", " ", title).strip(" -")
        if not title:
            return "Без названия"
        return Lg24Parser._ensure_brand_prefix(title, brand="LG")

    @staticmethod
    def _parse_first_number(value: str) -> float | None:
        if not value:
            return None
        cleaned = value.replace("\xa0", " ")
        match = re.search(r"(-?\d[\d\s]*(?:[.,]\d+)?)", cleaned)
        if not match:
            return None
        try:
            raw = match.group(1).replace(" ", "").replace(",", ".")
            return float(raw)
        except ValueError:
            return None

    @classmethod
    def _to_abs_url(cls, value: str, current_url: str) -> str:
        if not value:
            return ""
        if value.startswith("//"):
            return f"https:{value}"
        if value.startswith("/"):
            return f"{cls.BASE_URL}{value}"
        if value.startswith("http://") or value.startswith("https://"):
            return value
        return urljoin(current_url, value)

    @classmethod
    def _collect_images(cls, soup: BeautifulSoup, current_url: str) -> List[str]:
        seen: set[str] = set()
        images: List[str] = []

        for img in soup.select("div.woocommerce-product-gallery img"):
            for attr in ("data-large_image", "src", "data-src"):
                raw = img.get(attr, "")
                if not raw:
                    continue
                abs_url = cls._to_abs_url(raw, current_url)
                if not abs_url or abs_url.startswith("data:"):
                    continue
                if abs_url in seen:
                    continue
                seen.add(abs_url)
                images.append(abs_url)

        return images

    @classmethod
    def _collect_related_urls(cls, soup: BeautifulSoup, current_url: str) -> List[str]:
        related: List[str] = []
        # Use explicit product tag list to avoid noisy broad related grids.
        for link in soup.select("ul.item-tags a[href*='/product/']"):
            href = cls._to_abs_url(link.get("href", ""), current_url)
            if not href or href == current_url or href in related:
                continue
            related.append(href)
        return related

    @classmethod
    def _should_skip_spec(cls, key: str, value: str) -> bool:
        key_l = key.lower().strip()
        value_l = value.lower().strip()
        if value_l in {"", "-", "—"}:
            return True
        # Until file attachments are supported, documentation rows are noise.
        if any(marker in key_l for marker in cls._DOC_SPEC_KEY_MARKERS):
            return True
        if "скача" in value_l or value_l in {"download"}:
            if any(marker in key_l for marker in cls._DOC_SPEC_KEY_MARKERS):
                return True
        return False

    @staticmethod
    def _extract_breadcrumb_parts(soup: BeautifulSoup) -> List[str]:
        breadcrumb = soup.select_one(".woocommerce-breadcrumb")
        if not breadcrumb:
            return []
        parts: List[str] = []
        for node in breadcrumb.children:
            text = node.get_text(" ", strip=True) if hasattr(node, "get_text") else str(node).strip()
            text = re.sub(r"\s+", " ", text).strip()
            if not text:
                continue
            if re.fullmatch(r"[/›»>]+", text):
                continue
            parts.append(text)
        return parts

    @classmethod
    def _infer_series_from_context(cls, title: str, breadcrumb_parts: List[str]) -> str:
        candidates = [part for part in breadcrumb_parts if part]
        candidates.append(title)
        for candidate in candidates:
            normalized_candidate = candidate.casefold().replace("ё", "е")
            if normalized_candidate in cls._CATEGORY_STOP_PARTS:
                continue
            for series in cls._KNOWN_SERIES:
                if re.search(rf"(?<!\w){re.escape(series)}(?!\w)", candidate, flags=re.IGNORECASE):
                    return series
        return ""

    @staticmethod
    def _infer_type_specs_from_breadcrumb(parts: List[str]) -> Dict[str, str]:
        inferred: Dict[str, str] = {}
        for part in parts:
            p = part.lower().strip()
            if "кондиционеры для дома" in p or "для дома" in p:
                inferred.setdefault("Тип", "сплит-система")
            elif "мульти" in p:
                inferred.setdefault("Тип", "мульти-сплит-система")
            elif "полупром" in p or "полупромышлен" in p:
                inferred.setdefault("Тип", "полупромышленный кондиционер")

            if "настенн" in p:
                inferred.setdefault("Тип внутреннего блока", "настенный")
            elif "каналь" in p:
                inferred.setdefault("Тип внутреннего блока", "канальный")
            elif "кассет" in p:
                inferred.setdefault("Тип внутреннего блока", "кассетный")
            elif "напольно" in p or "потолоч" in p:
                inferred.setdefault("Тип внутреннего блока", "напольно-потолочный")
            elif "колон" in p:
                inferred.setdefault("Тип внутреннего блока", "колонный")
        if "Тип внутреннего блока" in inferred and "Тип" not in inferred:
            indoor = inferred.get("Тип внутреннего блока", "")
            if indoor == "настенный":
                inferred["Тип"] = "сплит-система"
            else:
                inferred["Тип"] = "полупромышленный кондиционер"
        return inferred

    @staticmethod
    def _infer_component_models(specs: Dict[str, str]) -> Dict[str, str]:
        model = re.sub(r"\s+", " ", str(specs.get("Модель") or specs.get("model") or "")).strip()
        if not model or "/" not in model:
            return {}

        parts = [part.strip() for part in re.split(r"\s*/\s*", model, maxsplit=1) if part.strip()]
        if len(parts) != 2:
            return {}

        return {
            "Модель внутреннего блока": parts[0],
            "Модель наружного блока": parts[1],
        }

    @staticmethod
    def _extract_specs(soup: BeautifulSoup) -> Dict[str, str]:
        specs: Dict[str, str] = {}

        # Main source on lg24: <section id="tab1"> ... <dl><dt>..</dt><dd>..</dd>
        for row in soup.select("section#tab1 dl"):
            dt = row.find("dt")
            dd = row.find("dd")
            if not dt or not dd:
                continue
            key = dt.get_text(" ", strip=True).replace("\xa0", " ").rstrip(":")
            value = dd.get_text(" ", strip=True).replace("\xa0", " ")
            if key and value and not Lg24Parser._should_skip_spec(key, value):
                specs[key] = value

        # Fallback source: standard WooCommerce attributes table.
        if not specs:
            for row in soup.select("table.woocommerce-product-attributes tr"):
                th = row.find("th")
                td = row.find("td")
                if not th or not td:
                    continue
                key = th.get_text(" ", strip=True).replace("\xa0", " ").rstrip(":")
                value = td.get_text(" ", strip=True).replace("\xa0", " ")
                if key and value and not Lg24Parser._should_skip_spec(key, value):
                    specs[key] = value

        return specs

    @classmethod
    def _extract_manuals(cls, soup: BeautifulSoup, current_url: str) -> List[Dict[str, str]]:
        manuals: List[Dict[str, str]] = []
        seen: set[str] = set()

        def collect_row(key_text: str, value_node) -> None:
            key = (key_text or "").replace("\xa0", " ").strip().rstrip(":")
            if not key:
                return
            key_l = key.lower()
            if not any(marker in key_l for marker in cls._DOC_SPEC_KEY_MARKERS):
                return

            links = value_node.select("a[href]") if value_node else []
            for link in links:
                href = cls._to_abs_url(link.get("href", ""), current_url)
                if not href or href in seen:
                    continue
                seen.add(href)
                manuals.append(
                    {
                        "kind": "manual",
                        "title": key,
                        "url": href,
                        "source": "lg24",
                    }
                )

        for row in soup.select("section#tab1 dl"):
            dt = row.find("dt")
            dd = row.find("dd")
            if not dt or not dd:
                continue
            collect_row(dt.get_text(" ", strip=True), dd)

        if manuals:
            return manuals

        for row in soup.select("table.woocommerce-product-attributes tr"):
            th = row.find("th")
            td = row.find("td")
            if not th or not td:
                continue
            collect_row(th.get_text(" ", strip=True), td)

        return manuals

    @staticmethod
    def _extract_metrics(specs: Dict[str, str], title: str) -> Dict[str, Any]:
        metrics: Dict[str, Any] = {
            "power_cooling": None,
            "power_heating": None,
            "area": 0,
            "is_inverter": False,
            "min_temp_heating": None,
        }

        for key, value in specs.items():
            key_lower = key.lower()
            value_lower = value.lower()

            if "инвертор" in key_lower or "тип системы" in key_lower:
                if "инвертор" in value_lower or value_lower.startswith("да"):
                    metrics["is_inverter"] = True

            if "площад" in key_lower:
                match = re.search(r"(\d+)", value)
                if match and not metrics["area"]:
                    metrics["area"] = int(match.group(1))

            if "мощност" in key_lower and "охлажд" in key_lower:
                parsed = Lg24Parser._parse_first_number(value)
                if parsed is not None:
                    metrics["power_cooling"] = parsed

            if "мощност" in key_lower and ("нагрев" in key_lower or "обогрев" in key_lower):
                parsed = Lg24Parser._parse_first_number(value)
                if parsed is not None:
                    metrics["power_heating"] = parsed

            if "температ" in key_lower and ("мин" in key_lower or "обогрев" in key_lower):
                match = re.search(r"(-\d+)", value)
                if match:
                    metrics["min_temp_heating"] = int(match.group(1))

        if not metrics["area"]:
            title_area = re.search(r"до\s*(\d+)\s*м", title.lower())
            if title_area:
                metrics["area"] = int(title_area.group(1))

        return metrics

    async def parse(self, url: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=20.0,
            headers=self._HEADERS,
        ) as client:
            response = await client.get(url)
            if response.status_code != 200:
                raise Exception(f"Ошибка загрузки страницы lg24.by: {response.status_code}")

        soup = BeautifulSoup(response.text, "html.parser")
        if not self._is_product_url(str(response.url)):
            raise ValueError("Lg24Parser.parse expects a product URL")

        h1 = soup.select_one("h1.product_title") or soup.select_one("h1.entry-title") or soup.select_one("h1")
        title_raw = h1.get_text(" ", strip=True) if h1 else "Без названия"
        title = self._normalize_model_title(title_raw)

        price = 0
        price_meta = soup.select_one('meta[itemprop="price"]')
        price_text = ""
        if price_meta:
            price_text = price_meta.get("content", "")
        if not price_text:
            price_el = soup.select_one("p.price") or soup.select_one(".summary p.price") or soup.select_one(".woocommerce-Price-amount")
            if price_el:
                price_text = price_el.get_text(" ", strip=True)
        parsed_price = self._parse_first_number(price_text)
        if parsed_price is not None:
            price = int(round(parsed_price))

        stock_el = soup.select_one("p.stock")
        availability = stock_el.get_text(" ", strip=True) if stock_el else ""
        in_stock = bool(availability) and ("нет в наличии" not in availability.lower())

        description_el = soup.select_one(".woocommerce-product-details__short-description") or soup.select_one("section#tab1")
        description = description_el.get_text("\n", strip=True) if description_el else ""

        specs = self._extract_specs(soup)
        # lg24.by catalog is LG-only; force canonical brand to avoid
        # mis-detection from series words in title (e.g. "Ultra").
        specs.setdefault("Бренд", "LG")
        breadcrumb_parts = self._extract_breadcrumb_parts(soup)
        for key, value in self._infer_type_specs_from_breadcrumb(breadcrumb_parts).items():
            specs.setdefault(key, value)
        series = self._infer_series_from_context(title, breadcrumb_parts)
        if series:
            specs.setdefault("Серия", series)
        for key, value in self._infer_component_models(specs).items():
            specs.setdefault(key, value)
        if availability:
            specs.setdefault("Наличие", availability)

        metrics = self._extract_metrics(specs, title)
        images = self._collect_images(soup, str(response.url))
        related_urls = self._collect_related_urls(soup, str(response.url))
        manuals = self._extract_manuals(soup, str(response.url))

        return {
            "title": title,
            "slug": self._slug_from_url(str(response.url)),
            "description": description,
            "price": price,
            "area": metrics["area"],
            "main_image": images[0] if images else "",
            "images": images[1:] if len(images) > 1 else [],
            "save_gallery": True,
            "categories": [],
            "specs": specs,
            "metrics": metrics,
            "related_urls": related_urls,
            "manuals": manuals,
            "availability": availability,
            "in_stock": in_stock,
        }
