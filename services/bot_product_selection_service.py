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
    INVERTER_TIERS = (
        ("optimal", "Оптимально", {"is_inverter": True, "sort": "balanced"}),
        ("premium", "Премиум", {"is_inverter": True, "sort": "premium"}),
    )
    ONOFF_TIERS = (
        ("onoff", "ON-OFF", {"is_inverter": False, "sort": "price"}),
    )
    DEFAULT_TAG_SLUGS = ["cat-household"]
    POWER_CLASSES = {
        "7": {"kw": 1.9, "area": (15, 24)},
        "9": {"kw": 2.6, "area": (25, 32)},
        "12": {"kw": 3.5, "area": (33, 42)},
        "18": {"kw": 5.3, "area": (45, 60)},
        "24": {"kw": 7.0, "area": (65, 80)},
        "36": {"kw": 10.5, "area": (90, 110)},
    }
    POWER_CLASS_ALIASES = {
        "7": ("семерка", "семерки", "семерок", "семерочка", "семерочки"),
        "9": ("девятка", "девятки", "девяток"),
        "12": ("двенашка", "двенашки", "двенадцатка", "двенадцатки"),
        "18": ("восемнашка", "восемнашки"),
        "24": ("двадцатьчетверка", "двадцатьчетверки"),
    }
    COUNT_WORDS = {
        "одна": 1,
        "один": 1,
        "две": 2,
        "два": 2,
        "три": 3,
        "четыре": 4,
    }

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

    @classmethod
    def _normalize_text(cls, text: str) -> str:
        return (text or "").casefold().replace("ё", "е")

    @classmethod
    def _normalize_power_code(cls, value: str) -> str | None:
        normalized = str(value or "").strip().lstrip("0") or "0"
        return normalized if normalized in cls.POWER_CLASSES else None

    @classmethod
    def _target_for_power_class(cls, code: str) -> dict[str, Any]:
        config = cls.POWER_CLASSES[code]
        area_min = int(config["area"][0])
        area_max = int(config["area"][1])
        kw = float(config["kw"])
        kw_text = str(kw).replace(".", ",")
        return {
            "kind": "power_class",
            "code": code,
            "label": f"{code} ({kw_text} кВт)",
            "area": area_min,
            "area_min": area_min,
            "area_max": area_max,
            "kw": kw,
        }

    @classmethod
    def _target_for_area(cls, area: int) -> dict[str, Any]:
        return {
            "kind": "area",
            "area": area,
            "area_min": area,
            "area_max": None,
            "label": f"{area} м²",
        }

    @classmethod
    def parse_selection_request(cls, text: str) -> dict[str, Any]:
        normalized = cls._normalize_text(text)
        max_targets = 6
        targets: list[dict[str, Any]] = []

        alias_to_code = {
            alias: code
            for code, aliases in cls.POWER_CLASS_ALIASES.items()
            for alias in aliases
        }
        alias_pattern = "|".join(sorted((re.escape(alias) for alias in alias_to_code), key=len, reverse=True))
        token_pattern = re.compile(
            rf"(?:(?P<count>\b\d{{1,2}}\b|{'|'.join(cls.COUNT_WORDS)})\s+)?(?P<alias>{alias_pattern})\b"
            r"|(?P<number>\b\d{1,3}\b)\s*(?P<unit>м2|м²|кв\.?|квадрат(?:ов|а)?|квадратный метр(?:ов|а)?)?",
            re.IGNORECASE,
        )

        for match in token_pattern.finditer(normalized):
            alias = match.group("alias")
            if alias:
                count_raw = match.group("count")
                count = cls.COUNT_WORDS.get(str(count_raw or "").strip(), None)
                if count is None:
                    count = int(count_raw) if str(count_raw or "").isdigit() else 1
                count = max(1, min(count, 6))
                code = alias_to_code[alias]
                targets.extend(cls._target_for_power_class(code) for _ in range(count))
            else:
                number_raw = match.group("number")
                if not number_raw:
                    continue
                value = int(number_raw)
                unit = match.group("unit")
                power_code = cls._normalize_power_code(number_raw)
                if unit:
                    if 8 <= value <= 120:
                        targets.append(cls._target_for_area(value))
                elif power_code:
                    targets.append(cls._target_for_power_class(power_code))
                elif 8 <= value <= 120:
                    targets.append(cls._target_for_area(value))

            if len(targets) >= max_targets:
                targets = targets[:max_targets]
                break

        compressor_mode = "mixed"
        mode_reason = ""
        if re.search(
            r"\b(серверн\w*|on[\s/-]?off|он[\s-]?офф|он[\s-]?оф|не\s+инвертор\w*|неинвертор\w*)\b",
            normalized,
        ):
            compressor_mode = "onoff_only"
            mode_reason = "серверная" if "серверн" in normalized else "ON-OFF"
        elif re.search(r"\b(инвертор\w*|inverter\w*)\b", normalized):
            compressor_mode = "inverter_only"
            mode_reason = "инверторы"

        return {
            "targets": targets,
            "compressor_mode": compressor_mode,
            "mode_reason": mode_reason,
        }

    @classmethod
    def _tiers_for_mode(cls, compressor_mode: str):
        if compressor_mode == "inverter_only":
            return cls.INVERTER_TIERS
        if compressor_mode == "onoff_only":
            return cls.ONOFF_TIERS
        return cls.TIERS

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

        if tier_key in {"budget", "onoff"}:
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
        parsed = cls.parse_selection_request(query)
        targets = parsed["targets"]
        if not targets:
            return {"areas": [], "message": "Не нашел мощность или площадь. Напишите, например: подбор 7,7,12 или 20 и 35 м²."}

        result: dict[str, Any] = {
            "areas": [],
            "compressor_mode": parsed["compressor_mode"],
            "mode_reason": parsed["mode_reason"],
        }
        tiers = cls._tiers_for_mode(parsed["compressor_mode"])
        for target in targets:
            area_payload = {
                "area": target["area"],
                "label": target["label"],
                "kind": target["kind"],
                "code": target.get("code"),
                "tiers": [],
            }
            seen_ids: set[int] = set()
            for tier_key, label, options in tiers:
                products = await ProductService.get_curated(
                    session,
                    area=target["area"],
                    area_min=target["area_min"],
                    area_max=target["area_max"],
                    is_inverter=bool(options["is_inverter"]),
                    tag_slugs=cls.DEFAULT_TAG_SLUGS,
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
        mode = selection.get("compressor_mode")
        if mode == "inverter_only":
            lines.append("Режим: только инверторы")
        elif mode == "onoff_only":
            reason = f" ({selection.get('mode_reason')})" if selection.get("mode_reason") else ""
            lines.append(f"Режим: только ON-OFF{reason}")
        for area in selection["areas"]:
            area_label = area.get("label") or f"{area['area']} м²"
            lines.extend(["", f"<b>{area_label}</b>"])
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
