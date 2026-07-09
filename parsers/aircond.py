import json
import re
from typing import Dict, Any, List
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .base import BaseParser


class AircondParser(BaseParser):
    """Parser for aircond.by product pages."""

    BASE_URL = "https://aircond.by"
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }

    def supports(self, url: str) -> bool:
        return "aircond.by" in url

    # ------------------------------------------------------------------
    # Spec extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_text(value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()

    @classmethod
    def _extract_boolean_icon_value(cls, cell) -> str | None:
        table_icon = cell.find("p", class_="table__icon")
        if table_icon:
            css_classes = table_icon.get("class", [])
            if "true" in css_classes:
                return "да"
            if "false" in css_classes:
                return "нет"

        svg = cell.find("svg")
        if not svg:
            return None

        classes = svg.get("class") or []
        if "lucide-check" in classes:
            return "да"
        if "lucide-x" in classes or "lucide-minus" in classes:
            return "нет"
        return None

    @classmethod
    def _extract_spec_value(cls, td_cell) -> str:
        """Extract value from a <td> cell in the specs table.

        Boolean rows use <p class="table__icon true"> / <p class="table__icon false">
        instead of text.
        """
        icon_value = cls._extract_boolean_icon_value(td_cell)
        if icon_value is not None:
            return icon_value

        return cls._clean_text(td_cell.get_text(" ", strip=True))

    @classmethod
    def _extract_specs(cls, soup: BeautifulSoup) -> Dict[str, str]:
        specs: Dict[str, str] = {}

        spec_table = soup.select_one(".product__specs table")
        if spec_table:
            for row in spec_table.find_all("tr"):
                th = row.find("th")
                td = row.find("td")
                if not th or not td:
                    continue
                key = cls._clean_text(th.get_text(" ", strip=True)).rstrip(":")
                value = cls._extract_spec_value(td)
                if key and value:
                    specs[key] = value

        modern_section = cls._find_section_by_heading(soup, "характеристики")
        if modern_section:
            for row in modern_section.find_all("div"):
                spans = row.find_all("span", recursive=False)
                if len(spans) < 2:
                    continue
                key = cls._clean_text(spans[0].get_text(" ", strip=True)).rstrip(":")
                value = cls._extract_spec_value(spans[1])
                if key and value:
                    specs[key] = value

        return specs

    @classmethod
    def _find_section_by_heading(cls, soup: BeautifulSoup, heading: str):
        target = heading.strip().lower()
        for header in soup.find_all(["h2", "h3"]):
            if cls._clean_text(header.get_text(" ", strip=True)).lower() == target:
                return header.parent
        return None

    @staticmethod
    def _iter_json_ld_objects(soup: BeautifulSoup):
        def walk(value):
            if isinstance(value, dict):
                yield value
                graph = value.get("@graph")
                if isinstance(graph, list):
                    for item in graph:
                        yield from walk(item)
            elif isinstance(value, list):
                for item in value:
                    yield from walk(item)

        for script in soup.find_all("script", type="application/ld+json"):
            raw = script.string or script.get_text()
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                continue
            yield from walk(parsed)

    @classmethod
    def _extract_product_schema(cls, soup: BeautifulSoup) -> Dict[str, Any]:
        for item in cls._iter_json_ld_objects(soup):
            item_type = item.get("@type")
            if item_type == "Product" or (
                isinstance(item_type, list) and "Product" in item_type
            ):
                return item
        return {}

    @staticmethod
    def _parse_price(raw: Any) -> int:
        if raw is None:
            return 0
        if isinstance(raw, (int, float)):
            return int(float(raw))

        match = re.search(r"\d[\d\s\xa0]*(?:[,.]\d+)?", str(raw))
        if not match:
            return 0
        value = match.group(0).replace(" ", "").replace("\xa0", "").replace(",", ".")
        try:
            return int(float(value))
        except ValueError:
            return 0

    # ------------------------------------------------------------------
    # Image extraction
    # ------------------------------------------------------------------

    @classmethod
    def _collect_images(cls, soup: BeautifulSoup) -> List[str]:
        """Collect high-quality product images from old and current aircond.by markup."""
        seen: set[str] = set()
        result: List[str] = []

        def add(src: str | None) -> None:
            if not src:
                return
            src = urljoin(cls.BASE_URL, src)
            if "/images/payment" in src or "/thumb-" in src:
                return
            if not (
                "/media/" in src
                or "/series/" in src
                or urlparse(src).netloc == "cdn.aircond.by"
            ):
                return
            if src not in seen:
                seen.add(src)
                result.append(src)

        product_schema = cls._extract_product_schema(soup)
        schema_images = product_schema.get("image")
        if isinstance(schema_images, str):
            add(schema_images)
        elif isinstance(schema_images, list):
            for src in schema_images:
                add(str(src))

        for img in soup.find_all("img"):
            add(img.get("src") or img.get("data-src"))

        return result

    # ------------------------------------------------------------------
    # Related products (series) extraction
    # ------------------------------------------------------------------

    @classmethod
    def _collect_related_urls(cls, soup: BeautifulSoup, current_url: str) -> List[str]:
        """Extract related variant URLs from old and current product markup."""
        related: List[str] = []

        current_absolute = current_url.rstrip("/")
        current_path = urlparse(current_url).path.rstrip("/")

        def add(href: str) -> None:
            absolute = urljoin(current_url, href).split("#", 1)[0].split("?", 1)[0]
            parsed = urlparse(absolute)
            path = parsed.path.rstrip("/")
            if absolute.rstrip("/") == current_absolute:
                return
            if path == "/split-sistemy" or not path.startswith("/split-sistemy/"):
                return
            if path == current_path:
                return
            if absolute not in related:
                related.append(absolute)

        for link in soup.select("a.series-products__link"):
            href = link.get("href", "")
            if not href:
                continue
            add(href)

        for link in soup.find_all("a", href=True):
            classes = link.get("class") or []
            if "rounded-md" not in classes or "border" not in classes:
                continue
            add(link["href"])

        return related

    @classmethod
    def _extract_description(cls, soup: BeautifulSoup, product_schema: Dict[str, Any]) -> str:
        descr_el = soup.select_one(".product__descr")
        if descr_el:
            return descr_el.get_text("\n", strip=True)

        schema_description = product_schema.get("description")
        if schema_description:
            return cls._clean_text(schema_description)

        description_section = cls._find_section_by_heading(soup, "описание")
        if not description_section:
            return ""
        prose = description_section.find(
            "div",
            class_=lambda classes: classes and "prose" in str(classes).split(),
        )
        target = prose or description_section
        return cls._clean_text(target.get_text(" ", strip=True).replace("Описание", "", 1))

    @classmethod
    def _build_metrics(cls, specs: Dict[str, str]) -> Dict[str, Any]:
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
            normalized_value = value.replace(",", ".")

            if "обслуживаемая площадь" in key_lower or "площадь помещения" in key_lower:
                m = re.search(r"(\d+)", value)
                if m and not metrics["area"]:
                    metrics["area"] = int(m.group(1))
            elif "инвертор" in key_lower:
                metrics["is_inverter"] = value_lower.startswith("да") or "инвертор" in value_lower
            elif "мощность охлаждения" in key_lower:
                m = re.search(r"([\d.]+)", normalized_value)
                if m:
                    metrics["power_cooling"] = float(m.group(1))
            elif "мощность обогрева" in key_lower:
                m = re.search(r"([\d.]+)", normalized_value)
                if m:
                    metrics["power_heating"] = float(m.group(1))
            elif "минимальная температура" in key_lower or "рабочая температура при обогреве" in key_lower:
                m = re.search(r"(-\d+)", value)
                if m:
                    metrics["min_temp_heating"] = int(m.group(1))

        return metrics

    # ------------------------------------------------------------------
    # Slug from URL
    # ------------------------------------------------------------------

    @staticmethod
    def _slug_from_url(url: str) -> str:
        """Extract a reasonable slug from an aircond.by product URL.

        Example URL: https://aircond.by/split-sistemy/mdv-integra-pro-inverter-.../
        We take the last meaningful path segment.
        """
        path = url.rstrip("/").split("?")[0]
        segments = [s for s in path.split("/") if s]
        return segments[-1] if segments else "unknown"

    # ------------------------------------------------------------------
    # Main parse
    # ------------------------------------------------------------------

    async def parse(self, url: str) -> Dict[str, Any]:
        """Parse a single product page on aircond.by."""

        async with httpx.AsyncClient(
            follow_redirects=True, timeout=15.0, headers=self._HEADERS
        ) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                raise Exception(
                    f"Ошибка загрузки страницы aircond.by: {resp.status_code}"
                )

        soup = BeautifulSoup(resp.text, "html.parser")
        product_schema = self._extract_product_schema(soup)

        # --- Title ---
        h1 = soup.select_one("h1.product__name") or soup.select_one("h1.page-title") or soup.find("h1")
        title = (
            h1.get_text(strip=True)
            if h1
            else self._clean_text(product_schema.get("name") or "Без названия")
        )

        # --- Price ---
        price = 0
        price_el = soup.select_one('.offer__price span[property="price"]')
        if price_el:
            raw = price_el.get("content") or price_el.get_text(strip=True)
            price = self._parse_price(raw)
        if not price:
            offers = product_schema.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            if isinstance(offers, dict):
                price = self._parse_price(offers.get("price"))
        if not price:
            fallback_price_el = soup.find(
                "span",
                class_=lambda classes: classes and "text-3xl" in str(classes).split(),
            )
            if fallback_price_el:
                price = self._parse_price(fallback_price_el.get_text(" ", strip=True))

        # --- Description ---
        description = self._extract_description(soup, product_schema)

        # --- Specs ---
        all_specs = self._extract_specs(soup)
        target_specs = self._build_metrics(all_specs)

        # --- Images ---
        images = self._collect_images(soup)
        main_image = images[0] if images else ""

        # --- Related ---
        related_urls = self._collect_related_urls(soup, url)

        # --- Slug ---
        slug = self._slug_from_url(url)

        return {
            "title": title,
            "slug": slug,
            "description": description,
            "price": price,
            "area": target_specs["area"],
            "main_image": main_image,
            "images": images[1:] if len(images) > 1 else [],
            "save_gallery": True,  # Signal to ImporterService to save gallery images
            "categories": [],
            "specs": all_specs,
            "metrics": target_specs,
            "related_urls": related_urls,
        }
