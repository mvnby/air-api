import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from services.product_service import ProductService


class BotProductSelectionService:
    TIERS = (
        ("budget", "Бюджетнее", {"is_inverter": False, "sort": "price"}),
        ("optimal", "Оптимально", {"is_inverter": True, "sort": "balanced"}),
        ("premium", "Премиум", {"is_inverter": True, "sort": "premium"}),
    )

    @staticmethod
    def product_url(product: dict[str, Any]) -> str:
        slug = str(product.get("slug") or "").strip()
        base = settings.PUBLIC_SITE_URL.rstrip("/") if getattr(settings, "PUBLIC_SITE_URL", "") else "https://mvn.by"
        return f"{base}/product/{slug}/" if slug else base

    @staticmethod
    def parse_areas(text: str) -> list[int]:
        areas: list[int] = []
        for match in re.finditer(r"\b(\d{1,3})\s*(?:м2|м²|кв|квадрат|квадратов)?\b", text.casefold()):
            value = int(match.group(1))
            if 8 <= value <= 120 and value not in areas:
                areas.append(value)
        return areas[:4]

    @staticmethod
    def availability_rank(product: dict[str, Any]) -> int:
        if int(product.get("vitebsk_qty") or 0) > 0:
            return 0
        if int(product.get("minsk_qty") or 0) > 0:
            return 1
        availability = str(product.get("availability_status") or "").strip().lower()
        if availability == "in_stock_now":
            return 0
        if availability == "available_2_3_days":
            return 1
        if availability == "check_availability":
            return 2
        return 3

    @staticmethod
    def _sort_for_tier(products: list[dict[str, Any]], tier_key: str) -> list[dict[str, Any]]:
        def price(product: dict[str, Any]) -> int:
            return int(product.get("price") or 0)

        if tier_key == "budget":
            return sorted(products, key=lambda item: (BotProductSelectionService.availability_rank(item), price(item)))
        if tier_key == "premium":
            return sorted(products, key=lambda item: (BotProductSelectionService.availability_rank(item), -price(item)))
        return sorted(products, key=lambda item: (BotProductSelectionService.availability_rank(item), abs(price(item))))

    @staticmethod
    def availability_text(product: dict[str, Any]) -> str:
        vitebsk_qty = int(product.get("vitebsk_qty") or 0)
        minsk_qty = int(product.get("minsk_qty") or 0)
        availability = str(product.get("availability_status") or "").strip().lower()
        if vitebsk_qty > 0:
            return f"Витебск: {vitebsk_qty} шт."
        if minsk_qty > 0:
            return f"Минск: {minsk_qty} шт., обычно 2-3 дня"
        if availability == "in_stock_now":
            return "В наличии"
        if availability == "available_2_3_days":
            return "Доступно 2-3 дня"
        if availability == "check_availability":
            return "Наличие уточнить"
        return "Нет в наличии"

    @classmethod
    async def build_selection(
        cls,
        session: AsyncSession,
        query: str,
        *,
        limit_per_tier: int = 1,
    ) -> dict[str, Any]:
        areas = cls.parse_areas(query)
        if not areas:
            return {"areas": [], "message": "Не нашел площадь. Напишите, например: подбор 20 и 35 м²."}

        result: dict[str, Any] = {"areas": []}
        for area in areas:
            area_payload = {"area": area, "tiers": []}
            seen_ids: set[int] = set()
            for tier_key, label, options in cls.TIERS:
                products = await ProductService.get_curated(
                    session,
                    area=area,
                    is_inverter=bool(options["is_inverter"]),
                    limit=12,
                )
                sorted_products = [
                    product
                    for product in cls._sort_for_tier(products, tier_key)
                    if int(product.get("id") or 0) not in seen_ids
                ]
                picked = sorted_products[:limit_per_tier]
                for product in picked:
                    seen_ids.add(int(product.get("id") or 0))
                area_payload["tiers"].append(
                    {
                        "key": tier_key,
                        "label": label,
                        "products": picked,
                    }
                )
            result["areas"].append(area_payload)
        return result

    @classmethod
    def format_selection(cls, selection: dict[str, Any]) -> str:
        if not selection.get("areas"):
            return selection.get("message") or "Ничего не подобрал."

        lines = ["<b>Подбор кондиционеров для клиента</b>"]
        for area in selection["areas"]:
            lines.extend(["", f"<b>{area['area']} м²</b>"])
            for tier in area["tiers"]:
                products = tier.get("products") or []
                if not products:
                    lines.append(f"{tier['label']}: нет подходящих моделей")
                    continue
                product = products[0]
                reason = cls.availability_text(product)
                lines.append(
                    f"{tier['label']}: {product.get('title')} - {product.get('price')} руб.\n"
                    f"{reason}\n"
                    f"{cls.product_url(product)}"
                )
        return "\n".join(lines)
