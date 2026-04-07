import re
from typing import Dict, Any, List
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from .base import BaseParser


class TvoyKlimatParser(BaseParser):
    """Parser for tvoy-klimat.by product pages.

    HTML selectors (Bitrix-based):
        Title:       h1 / h1.switcher-title
        Price:       meta[itemprop="price"] (content attr) or .price__new-val
        Description: .detail_text / #descr
        Specs:       .properties-group__item  →  .properties-group__name (key)
                                                .properties-group__value (value)
        Images:      .detail-gallery-big__link (href for full-size image)
        Related:     .image-list__link / .dark_link.switcher-title
        Breadcrumbs: .breadcrumbs__link
    """

    BASE_URL = "https://tvoy-klimat.by"
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }

    def supports(self, url: str) -> bool:
        return "tvoy-klimat.by" in url

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @classmethod
    def _collect_images(cls, soup: BeautifulSoup) -> List[str]:
        """Collect full-size product images from the gallery.

        tvoy-klimat.by stores thumbnails in <img> and links to full-size
        images via <a class="detail-gallery-big__link" href="...">.
        Fallback: look for <img> inside .detail-gallery if no <a> found.
        """
        seen: set[str] = set()
        result: List[str] = []

        # Primary: gallery links (full-size images)
        for link in soup.select("a.detail-gallery-big__link"):
            href = link.get("href", "")
            if not href:
                continue
            if href.startswith("/"):
                href = f"{cls.BASE_URL}{href}"
            if href not in seen:
                seen.add(href)
                result.append(href)

        # Fallback: if no gallery links, grab <img> with /upload/iblock/
        if not result:
            for img in soup.select(".detail-gallery img, .gallery img, .product-detail img"):
                src = img.get("src") or img.get("data-src") or ""
                if "/upload/" not in src:
                    continue
                if src.startswith("/"):
                    src = f"{cls.BASE_URL}{src}"
                if src not in seen:
                    seen.add(src)
                    result.append(src)

        return result

    @classmethod
    def _collect_related_urls(cls, soup: BeautifulSoup, current_url: str) -> List[str]:
        """Extract related product URLs from 'Вам также может понравиться'.

        Looks for product links in the recommendation section.
        """
        related: List[str] = []
        # Look in recommendation / related sections
        for link in soup.select(
            ".catalog-section-list a.dark_link, "
            ".viewed-products a.dark_link, "
            ".catalog-viewed a[href*='/catalog/'], "
            "a.image-list__link"
        ):
            href = link.get("href", "")
            if not href or not href.startswith("/catalog/"):
                continue
            full = f"{cls.BASE_URL}{href}"
            if full != current_url and full not in related:
                related.append(full)
        return related

    @staticmethod
    def _slug_from_url(url: str) -> str:
        """Extract slug from the last URL path segment.

        Example: .../kassetnyy-konditsioner-tcl-tca-48chrh-dv7/ → kassetnyy-konditsioner-tcl-tca-48chrh-dv7
        """
        path = url.rstrip("/").split("?")[0]
        segments = [s for s in path.split("/") if s]
        return segments[-1] if segments else "unknown"

    # ------------------------------------------------------------------
    # Main parse
    # ------------------------------------------------------------------

    async def parse(self, url: str) -> Dict[str, Any]:
        """Parse a single product page on tvoy-klimat.by."""

        async with httpx.AsyncClient(
            follow_redirects=True, timeout=15.0, headers=self._HEADERS
        ) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                raise Exception(
                    f"Ошибка загрузки страницы tvoy-klimat.by: {resp.status_code}"
                )

        soup = BeautifulSoup(resp.text, "html.parser")

        # --- Title ---
        h1 = soup.select_one("h1.switcher-title") or soup.select_one("h1")
        title = h1.get_text(strip=True) if h1 else "Без названия"

        # --- Price ---
        price = 0
        # Prefer structured meta tag
        price_meta = soup.select_one('meta[itemprop="price"]')
        if price_meta:
            raw = price_meta.get("content", "")
            try:
                price = int(float(raw.replace(" ", "").replace("\xa0", "")))
            except (ValueError, TypeError):
                pass
        # Fallback: visible price element
        if not price:
            price_el = soup.select_one(".price__new-val")
            if price_el:
                raw = re.sub(r"[^\d.,]", "", price_el.get_text(strip=True))
                try:
                    price = int(float(raw.replace(",", ".")))
                except (ValueError, TypeError):
                    pass

        # --- Description ---
        descr_el = soup.select_one(".detail_text") or soup.select_one("#descr")
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

        for item in soup.select(".properties-group__item"):
            name_el = item.select_one(".properties-group__name")
            val_el = item.select_one(".properties-group__value")
            if not name_el or not val_el:
                continue

            key = name_el.get_text(" ", strip=True).replace("\xa0", " ").rstrip(":")
            value = val_el.get_text(" ", strip=True).replace("\xa0", " ")

            all_specs[key] = value

            key_lower = key.lower()

            # Area
            if "площадь" in key_lower and ("обслуж" in key_lower or "помещ" in key_lower or "охлажд" in key_lower):
                m = re.search(r"(\d+)", value)
                if m and not target_specs["area"]:
                    target_specs["area"] = int(m.group(1))

            # Inverter
            elif "инверторн" in key_lower or "тип компрессора" in key_lower:
                val_lower = value.lower()
                target_specs["is_inverter"] = (
                    val_lower.startswith("да")
                    or "инвертор" in val_lower
                )

            # Cooling power
            elif "мощность" in key_lower and "охлажд" in key_lower:
                m = re.search(r"([\d.]+)", value)
                if m:
                    target_specs["power_cooling"] = float(m.group(1))

            # Heating power
            elif "мощность" in key_lower and ("обогрев" in key_lower or "нагрев" in key_lower):
                m = re.search(r"([\d.]+)", value)
                if m:
                    target_specs["power_heating"] = float(m.group(1))

            # Min temperature (heating)
            elif "минимальная температура" in key_lower or "мин" in key_lower and "темп" in key_lower:
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
            "save_gallery": True,
            "categories": [],
            "specs": all_specs,
            "metrics": target_specs,
            "related_urls": related_urls,
        }
