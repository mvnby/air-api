import re
from typing import Any, Dict, List
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from .base import BaseParser


class HaierProffParser(BaseParser):
    """Parser for haierproff.ru conditioner catalog product pages."""

    BASE_URL = "https://haierproff.ru"
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    }

    def supports(self, url: str) -> bool:
        return "haierproff.ru" in url and "/catalog/cond/products/" in url

    @staticmethod
    def _slug_from_url(url: str) -> str:
        path = url.rstrip("/").split("?")[0]
        segments = [segment for segment in path.split("/") if segment]
        return segments[-1] if segments else "unknown"

    @staticmethod
    def _normalize_title(raw_title: str) -> str:
        title = re.sub(r"\s+", " ", (raw_title or "").strip())
        if not title:
            return "Без названия"
        if not re.match(r"^haier\b", title, flags=re.IGNORECASE):
            title = f"Haier {title}"
        return title

    @staticmethod
    def _extract_series_from_title(title: str) -> str | None:
        match = re.search(r"(?:^|\s)Серия\s+(.+)$", title, flags=re.IGNORECASE)
        if not match:
            return None
        series = re.sub(r"\s+", " ", match.group(1)).strip(" -")
        return series or None

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
        return bool(
            soup.select_one(".product-page__title")
            and soup.select_one(".product-page__price")
            and soup.select_one(".spec-l__item")
        )

    @classmethod
    def _collect_images(cls, soup: BeautifulSoup, current_url: str) -> List[str]:
        seen: set[str] = set()
        images: List[str] = []

        for img in soup.select(".gallery__image-list img, .gallery img"):
            src = img.get("src") or img.get("data-src") or ""
            abs_url = cls._to_abs_url(src, current_url)
            if not abs_url or abs_url.startswith("data:") or abs_url in seen:
                continue
            seen.add(abs_url)
            images.append(abs_url)

        return images

    @classmethod
    def _collect_related_urls(cls, soup: BeautifulSoup, current_url: str) -> List[str]:
        related: List[str] = []
        for link in soup.select("a[href*='/catalog/cond/products/']"):
            href = cls._to_abs_url(link.get("href", ""), current_url)
            if not href or href == current_url or href in related:
                continue
            related.append(href)
        return related

    @staticmethod
    def _extract_specs(soup: BeautifulSoup) -> Dict[str, str]:
        specs: Dict[str, str] = {}
        for row in soup.select(".spec-l__item"):
            key_el = row.select_one(".spec-l__item-label")
            val_el = row.select_one(".spec-l__item-value")
            if not key_el or not val_el:
                continue
            key = key_el.get_text(" ", strip=True).replace("\xa0", " ").rstrip(":")
            value = val_el.get_text(" ", strip=True).replace("\xa0", " ")
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
        has_explicit_cooling = False
        has_explicit_heating = False

        for key, value in specs.items():
            key_lower = key.lower()
            value_lower = value.lower()

            if "инвертор" in key_lower:
                if "неинвертор" in key_lower:
                    if value_lower.startswith("да"):
                        metrics["is_inverter"] = False
                    elif value_lower.startswith("нет"):
                        metrics["is_inverter"] = True
                else:
                    metrics["is_inverter"] = value_lower.startswith("да") or "инвертор" in value_lower

            if "площад" in key_lower:
                numbers = re.findall(r"\d+", value)
                if numbers:
                    metrics["area"] = max(int(num) for num in numbers)

            if ("охлаждение" in key_lower or "мощность охлаждения" in key_lower) and "квт" in key_lower:
                parsed = HaierProffParser._parse_first_number(value)
                if parsed is not None:
                    is_derived_power = any(token in key_lower for token in ("потребля", "потреблен", "годов", "/г"))
                    if not is_derived_power:
                        metrics["power_cooling"] = parsed
                        has_explicit_cooling = True
                    elif not has_explicit_cooling and metrics["power_cooling"] is None:
                        metrics["power_cooling"] = parsed

            if ("нагрев" in key_lower or "обогрев" in key_lower or "мощность нагрева" in key_lower) and "квт" in key_lower:
                parsed = HaierProffParser._parse_first_number(value)
                if parsed is not None:
                    is_derived_power = any(token in key_lower for token in ("потребля", "потреблен", "годов", "/г"))
                    if not is_derived_power:
                        metrics["power_heating"] = parsed
                        has_explicit_heating = True
                    elif not has_explicit_heating and metrics["power_heating"] is None:
                        metrics["power_heating"] = parsed

            if "нагрев" in key_lower and "°" in key_lower:
                match = re.search(r"(-\d+)", value)
                if match:
                    metrics["min_temp_heating"] = int(match.group(1))

        if not metrics["area"]:
            title_area = re.search(r"(\d+)\s*м", title.lower())
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
                raise Exception(f"Ошибка загрузки страницы haierproff.ru: {response.status_code}")

        soup = BeautifulSoup(response.text, "html.parser")
        if not self._looks_like_product_page(soup):
            raise ValueError("URL haierproff.ru не похож на карточку товара кондиционера.")

        title_el = soup.select_one(".product-page__title")
        title_raw = title_el.get_text(" ", strip=True) if title_el else "Без названия"
        title = self._normalize_title(title_raw)

        price_text = ""
        price_el = soup.select_one(".product-page__price")
        if price_el:
            price_text = price_el.get_text(" ", strip=True)
        parsed_price = self._parse_first_number(price_text)
        price = int(round(parsed_price)) if parsed_price is not None else 0

        features = [item.get_text(" ", strip=True) for item in soup.select(".feature-s-list__item") if item.get_text(" ", strip=True)]
        description_parts = []
        if features:
            description_parts.append("Преимущества: " + ", ".join(features))
        description_parts.append(title)
        description = "\n".join(dict.fromkeys(description_parts))

        specs = self._extract_specs(soup)
        series = self._extract_series_from_title(title)
        if series:
            specs.setdefault("Серия", series)
        metrics = self._extract_metrics(specs, title)
        images = self._collect_images(soup, str(response.url))
        related_urls = self._collect_related_urls(soup, str(response.url))

        return {
            "title": title,
            "slug": self._slug_from_url(str(response.url)),
            "description": description,
            "price": price,
            "price_currency": "RUB",
            "area": metrics["area"],
            "main_image": images[0] if images else "",
            "images": images[1:] if len(images) > 1 else [],
            "save_gallery": True,
            "categories": [],
            "specs": specs,
            "metrics": metrics,
            "related_urls": related_urls,
            "availability": "В наличии",
            "in_stock": True,
        }
