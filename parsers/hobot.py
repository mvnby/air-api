import re
from typing import Any, Dict, List
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from .base import BaseParser


class HobotParser(BaseParser):
    """Parser for hobot.by product pages."""

    BASE_URL = "https://www.hobot.by"
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    }

    def supports(self, url: str) -> bool:
        return "hobot.by" in url

    @staticmethod
    def _slug_from_url(url: str) -> str:
        path = url.rstrip("/").split("?")[0]
        segments = [segment for segment in path.split("/") if segment]
        return segments[-1] if segments else "unknown"

    @staticmethod
    def _normalize_model_title(raw_title: str) -> str:
        title = re.sub(r"\s+", " ", (raw_title or "").strip())
        if not title:
            return "Без названия"

        title = re.sub(
            r"^(?:(?:кассетн(?:ый|ая|ое|ые)|настенн(?:ый|ая|ое|ые)|канальн(?:ый|ая|ое|ые)|"
            r"напольно-потолочн(?:ый|ая|ое|ые)|мобильн(?:ый|ая|ое|ые)|бытов(?:ой|ая|ое|ые)|"
            r"колонн(?:ый|ая|ое|ые)|универсальн(?:ый|ая|ое|ые)|инверторн(?:ый|ая|ое|ые)|"
            r"полупромышленн(?:ый|ая|ое|ые))\s+)+",
            "",
            title,
            flags=re.IGNORECASE,
        )

        title = re.sub(
            r"^(?:кондиционер|сплит[\s-]?система|мульти[\s-]?сплит[\s-]?система|внутренний\s+блок|наружный\s+блок)\s+",
            "",
            title,
            flags=re.IGNORECASE,
        )
        title = re.sub(r"\s+", " ", title).strip(" -")
        return title or "Без названия"

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

    @staticmethod
    def _looks_like_product_page(soup: BeautifulSoup) -> bool:
        if soup.select_one("table.product-specs__table"):
            return True
        if soup.select_one('meta[itemprop="price"]'):
            return True
        if soup.select_one(".buy_block-availability .isAvailable"):
            return True
        return False

    @staticmethod
    def _extract_specs(soup: BeautifulSoup) -> Dict[str, str]:
        specs: Dict[str, str] = {}
        for row in soup.select("table.product-specs__table tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) != 2:
                continue
            key = cells[0].get_text(" ", strip=True).replace("\xa0", " ").rstrip(":")
            value = cells[1].get_text(" ", strip=True).replace("\xa0", " ")
            if key and value:
                specs[key] = value
        return specs

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

            if "инвертор" in key_lower:
                metrics["is_inverter"] = (
                    value_lower.startswith("да")
                    or "есть" in value_lower
                    or value_lower in {"+", "✓", "✔"}
                    or "инвертор" in value_lower
                )

            if "площад" in key_lower:
                match = re.search(r"(\d+)", value)
                if match and not metrics["area"]:
                    metrics["area"] = int(match.group(1))

            if "мощност" in key_lower and "охлажд" in key_lower:
                parsed = HobotParser._parse_first_number(value)
                if parsed is not None:
                    metrics["power_cooling"] = parsed

            if "мощност" in key_lower and ("обогрев" in key_lower or "нагрев" in key_lower):
                parsed = HobotParser._parse_first_number(value)
                if parsed is not None:
                    metrics["power_heating"] = parsed

            if "температ" in key_lower and ("мин" in key_lower or "обогрев" in key_lower):
                match = re.search(r"(-\d+)", value)
                if match:
                    metrics["min_temp_heating"] = int(match.group(1))

        if not metrics["area"]:
            title_area = re.search(r"(\d+)\s*м", title.lower())
            if title_area:
                metrics["area"] = int(title_area.group(1))

        return metrics

    @classmethod
    def _collect_images(cls, soup: BeautifulSoup, current_url: str) -> List[str]:
        seen: set[str] = set()
        images: List[str] = []

        for link in soup.select("a[data-fancybox], a.fancy"):
            href = cls._to_abs_url(link.get("href", ""), current_url)
            if not href or href in seen:
                continue
            if href.startswith("data:"):
                continue
            if not any(ext in href.lower() for ext in (".jpg", ".jpeg", ".png", ".webp", "/upload/")):
                continue
            seen.add(href)
            images.append(href)

        if not images:
            for img in soup.select("img[src], img[data-src]"):
                raw = img.get("data-src") or img.get("src") or ""
                abs_url = cls._to_abs_url(raw, current_url)
                if not abs_url or abs_url.startswith("data:") or abs_url in seen:
                    continue
                if "/upload/" not in abs_url:
                    continue
                seen.add(abs_url)
                images.append(abs_url)

        return images

    @classmethod
    async def _choose_best_image_urls(cls, client: httpx.AsyncClient, image_urls: List[str]) -> List[str]:
        """Prefer original /upload/iblock images over resize_cache where possible."""

        async def exists(url: str) -> bool:
            try:
                resp = await client.head(url, timeout=10.0)
                if resp.status_code == 405:
                    resp = await client.get(url, timeout=10.0)
                return resp.status_code == 200
            except Exception:
                return False

        result: List[str] = []
        seen: set[str] = set()
        for url in image_urls:
            best_url = url
            match = re.search(
                r"/upload/resize_cache/(?:webp/)?resize_cache/iblock/([^/]+)/[^/]+/([^/?#]+)",
                url,
                re.IGNORECASE,
            )
            if match:
                folder = match.group(1)
                filename = match.group(2)
                filename_stem = filename.rsplit(".", 1)[0]
                candidates = [
                    f"{cls.BASE_URL}/upload/iblock/{folder}/{filename_stem}.jpg",
                    f"{cls.BASE_URL}/upload/iblock/{folder}/{filename_stem}.jpeg",
                    f"{cls.BASE_URL}/upload/iblock/{folder}/{filename_stem}.png",
                    f"{cls.BASE_URL}/upload/iblock/{folder}/{filename_stem}.webp",
                    f"{cls.BASE_URL}/upload/iblock/{folder}/{filename}",
                ]
                for candidate in candidates:
                    if await exists(candidate):
                        best_url = candidate
                        break

            if best_url not in seen:
                seen.add(best_url)
                result.append(best_url)

        return result

    @classmethod
    def _collect_related_urls(cls, soup: BeautifulSoup, current_url: str) -> List[str]:
        related: List[str] = []
        current_slug = cls._slug_from_url(current_url)

        for link in soup.select("a.dark_link[href*='/catalog/'], a.product-item__title[href*='/catalog/']"):
            href = cls._to_abs_url(link.get("href", ""), current_url)
            if not href or href == current_url or href in related:
                continue
            slug = cls._slug_from_url(href)
            if slug == current_slug:
                continue
            # Product links are usually deeper than pure categories.
            path_segments = [segment for segment in href.rstrip("/").split("/") if segment]
            if "catalog" in path_segments:
                idx = path_segments.index("catalog")
                if len(path_segments[idx + 1 :]) < 2:
                    continue
            related.append(href)

        return related

    async def parse(self, url: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=20.0,
            headers=self._HEADERS,
        ) as client:
            response = await client.get(url)
            if response.status_code != 200:
                raise Exception(f"Ошибка загрузки страницы hobot.by: {response.status_code}")

        soup = BeautifulSoup(response.text, "html.parser")

        h1 = soup.select_one("h1")
        title_raw = h1.get_text(" ", strip=True) if h1 else "Без названия"
        title = self._normalize_model_title(title_raw)
        if "страница не найдена" in title.lower():
            raise ValueError("URL hobot.by не найден (404-шаблон страницы).")
        if not self._looks_like_product_page(soup):
            raise ValueError("URL hobot.by не похож на карточку товара.")

        price = 0
        price_meta = soup.select_one('meta[itemprop="price"]')
        price_text = price_meta.get("content", "") if price_meta else ""
        if not price_text:
            price_el = soup.select_one(".price-main.price") or soup.select_one(".price")
            if price_el:
                price_text = price_el.get_text(" ", strip=True)
        parsed_price = self._parse_first_number(price_text)
        if parsed_price is not None:
            price = int(round(parsed_price))

        availability_el = soup.select_one(".buy_block-availability .isAvailable .available")
        availability = availability_el.get_text(" ", strip=True) if availability_el else ""
        if not availability:
            raw_block = soup.select_one(".buy_block-availability .isAvailable")
            availability = raw_block.get_text(" ", strip=True) if raw_block else ""
        in_stock = bool(availability) and ("нет" not in availability.lower())

        description = ""
        for block in soup.select(".detail_text"):
            text = block.get_text("\n", strip=True)
            if text and len(text) > len(description):
                description = text

        specs = self._extract_specs(soup)
        # Presence from source page is decorative and can be stale.
        # Real stock is synced from price mapping, so don't store it in specs.
        specs.pop("Наличие", None)

        metrics = self._extract_metrics(specs, title)
        images = self._collect_images(soup, str(response.url))
        if images:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=15.0,
                headers=self._HEADERS,
            ) as image_client:
                images = await self._choose_best_image_urls(image_client, images)
        # User decision: disable related crawling for hobot to avoid mass unintended imports.
        related_urls: List[str] = []

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
            "availability": availability,
            "in_stock": in_stock,
        }
