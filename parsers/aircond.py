import re
from typing import Dict, Any, List
from urllib.parse import urljoin

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
    def _extract_spec_value(td_cell) -> str:
        """Extract value from a <td> cell in the specs table.

        Boolean rows use <p class="table__icon true"> / <p class="table__icon false">
        instead of text.
        """
        true_icon = td_cell.find("p", class_="table__icon")
        if true_icon:
            css_classes = true_icon.get("class", [])
            if "true" in css_classes:
                return "да"
            if "false" in css_classes:
                return "нет"

        return td_cell.get_text(" ", strip=True).replace("\xa0", " ")

    # ------------------------------------------------------------------
    # Image extraction
    # ------------------------------------------------------------------

    @classmethod
    def _collect_images(cls, soup: BeautifulSoup) -> List[str]:
        """Collect high-quality webp/product images from the page.

        Looks for <img> tags whose src contains '/media/' — these are
        product/series photos hosted on aircond.by in webp format.
        """
        seen: set[str] = set()
        result: List[str] = []

        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or ""
            if "/media/" not in src:
                continue
            # Make absolute if relative
            if src.startswith("/"):
                src = f"{cls.BASE_URL}{src}"
            if src not in seen:
                seen.add(src)
                result.append(src)

        return result

    # ------------------------------------------------------------------
    # Related products (series) extraction
    # ------------------------------------------------------------------

    @classmethod
    def _collect_related_urls(cls, soup: BeautifulSoup, current_url: str) -> List[str]:
        """Extract hrefs from .series-products__link elements."""
        related: List[str] = []
        for link in soup.select("a.series-products__link"):
            href = link.get("href", "")
            if not href:
                continue
            # Make absolute
            if href.startswith("/"):
                href = f"{cls.BASE_URL}{href}"
            elif not href.startswith("http"):
                href = urljoin(current_url, href)
            if href != current_url and href not in related:
                related.append(href)
        return related

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

        # --- Title ---
        h1 = soup.select_one("h1.product__name")
        title = h1.get_text(strip=True) if h1 else "Без названия"

        # --- Price ---
        price = 0
        price_el = soup.select_one('.offer__price span[property="price"]')
        if price_el:
            raw = price_el.get("content") or price_el.get_text(strip=True)
            try:
                price = int(float(raw.replace(" ", "").replace("\xa0", "")))
            except (ValueError, TypeError):
                pass

        # --- Description ---
        descr_el = soup.select_one(".product__descr")
        description = descr_el.get_text("\n", strip=True) if descr_el else ""

        # --- Specs ---
        all_specs: Dict[str, str] = {}
        target_specs: Dict[str, Any] = {
            "power_cooling": None,
            "power_heating": None,
            "area": 0,
            "is_inverter": False,
            "min_temp_heating": None,
        }

        spec_table = soup.select_one(".product__specs table")
        if spec_table:
            for row in spec_table.find_all("tr"):
                th = row.find("th")
                td = row.find("td")
                if not th or not td:
                    continue
                key = th.get_text(" ", strip=True).replace("\xa0", " ").rstrip(":")
                value = self._extract_spec_value(td)

                all_specs[key] = value

                key_lower = key.lower()

                # Area
                if "обслуживаемая площадь" in key_lower or "площадь помещения" in key_lower:
                    m = re.search(r"(\d+)", value)
                    if m and not target_specs["area"]:
                        target_specs["area"] = int(m.group(1))

                # Inverter
                elif "инверторн" in key_lower:
                    target_specs["is_inverter"] = value.lower().startswith("да")

                # Cooling power
                elif "мощность охлаждения" in key_lower:
                    m = re.search(r"([\d.]+)", value)
                    if m:
                        target_specs["power_cooling"] = float(m.group(1))

                # Heating power
                elif "мощность обогрева" in key_lower:
                    m = re.search(r"([\d.]+)", value)
                    if m:
                        target_specs["power_heating"] = float(m.group(1))

                # Min temperature (heating)
                elif "минимальная температура" in key_lower or "рабочая температура при обогреве" in key_lower:
                    m = re.search(r"(-\d+)", value)
                    if m:
                        target_specs["min_temp_heating"] = int(m.group(1))

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
