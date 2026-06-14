import json
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from models import GlobalConfig
from services.product_service import ProductService


class BotProductSelectionService:
    CONFIG_KEY = "bot_product_selection_rules"
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

    @classmethod
    def _serialize_tiers(cls, tiers) -> list[dict[str, Any]]:
        return [
            {
                "key": key,
                "label": label,
                "is_inverter": bool(options.get("is_inverter")),
                "sort": str(options.get("sort") or "balanced"),
            }
            for key, label, options in tiers
        ]

    @classmethod
    def default_rules(cls) -> dict[str, Any]:
        return {
            "power_classes": {
                code: {
                    "kw": float(config["kw"]),
                    "area_min": int(config["area"][0]),
                    "area_max": int(config["area"][1]),
                }
                for code, config in cls.POWER_CLASSES.items()
            },
            "default_tag_slugs": list(cls.DEFAULT_TAG_SLUGS),
            "tiers": {
                "mixed": cls._serialize_tiers(cls.TIERS),
                "inverter_only": cls._serialize_tiers(cls.INVERTER_TIERS),
                "onoff_only": cls._serialize_tiers(cls.ONOFF_TIERS),
            },
        }

    @staticmethod
    def _coerce_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "да"}
        return bool(value)

    @classmethod
    def _normalize_power_classes(cls, raw: Any) -> dict[str, dict[str, Any]]:
        normalized = dict(cls.default_rules()["power_classes"])
        if not isinstance(raw, dict):
            return normalized

        for raw_code, raw_config in raw.items():
            code = cls._normalize_power_code(str(raw_code), {"power_classes": normalized})
            if code is None:
                code = str(raw_code or "").strip().lstrip("0")
            if not code or not code.isdigit() or not isinstance(raw_config, dict):
                continue

            try:
                kw = float(raw_config["kw"])
                if "area" in raw_config and isinstance(raw_config["area"], (list, tuple)):
                    area_min = int(raw_config["area"][0])
                    area_max = int(raw_config["area"][1])
                else:
                    area_min = int(raw_config["area_min"])
                    area_max = int(raw_config["area_max"])
            except (KeyError, TypeError, ValueError, IndexError):
                continue

            if kw <= 0 or area_min < 1 or area_max < area_min or area_max > 200:
                continue
            normalized[code] = {"kw": kw, "area_min": area_min, "area_max": area_max}
        return normalized

    @classmethod
    def _normalize_tiers(cls, raw: Any) -> dict[str, tuple[tuple[str, str, dict[str, Any]], ...]]:
        defaults = {
            "mixed": cls.TIERS,
            "inverter_only": cls.INVERTER_TIERS,
            "onoff_only": cls.ONOFF_TIERS,
        }
        if not isinstance(raw, dict):
            return defaults

        normalized = dict(defaults)
        for mode in defaults:
            raw_items = raw.get(mode)
            if not isinstance(raw_items, list):
                continue

            tier_items: list[tuple[str, str, dict[str, Any]]] = []
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                key = str(item.get("key") or "").strip()
                label = str(item.get("label") or "").strip()
                if not key or not label:
                    continue
                tier_items.append(
                    (
                        key,
                        label,
                        {
                            "is_inverter": cls._coerce_bool(item.get("is_inverter")),
                            "sort": str(item.get("sort") or "balanced").strip() or "balanced",
                        },
                    )
                )
            if tier_items:
                normalized[mode] = tuple(tier_items)
        return normalized

    @classmethod
    def normalize_rules(cls, raw: Any) -> dict[str, Any]:
        payload = raw if isinstance(raw, dict) else {}
        tag_slugs = payload.get("default_tag_slugs")
        if not isinstance(tag_slugs, list):
            tag_slugs = payload.get("tag_slugs")
        normalized_tag_slugs = [
            str(slug).strip()
            for slug in (tag_slugs if isinstance(tag_slugs, list) else cls.DEFAULT_TAG_SLUGS)
            if str(slug).strip()
        ]
        if not normalized_tag_slugs:
            normalized_tag_slugs = list(cls.DEFAULT_TAG_SLUGS)

        return {
            "power_classes": cls._normalize_power_classes(payload.get("power_classes")),
            "default_tag_slugs": normalized_tag_slugs,
            "tiers": cls._normalize_tiers(payload.get("tiers")),
        }

    @classmethod
    async def get_selection_rules(cls, session: AsyncSession) -> dict[str, Any]:
        try:
            result = await session.execute(select(GlobalConfig).where(GlobalConfig.key == cls.CONFIG_KEY))
            config = result.scalar_one_or_none()
            raw_value = json.loads(config.value) if config and config.value else {}
        except Exception:
            raw_value = {}
        return cls.normalize_rules(raw_value)

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
    def _normalize_power_code(cls, value: str, rules: dict[str, Any] | None = None) -> str | None:
        normalized = str(value or "").strip().lstrip("0") or "0"
        power_classes = (rules or {}).get("power_classes") if isinstance(rules, dict) else None
        if not isinstance(power_classes, dict):
            power_classes = cls.default_rules()["power_classes"]
        return normalized if normalized in power_classes else None

    @classmethod
    def _target_for_power_class(cls, code: str, rules: dict[str, Any] | None = None) -> dict[str, Any]:
        power_classes = (rules or {}).get("power_classes") if isinstance(rules, dict) else None
        if not isinstance(power_classes, dict):
            power_classes = cls.default_rules()["power_classes"]
        config = power_classes[code]
        area_min = int(config["area_min"])
        area_max = int(config["area_max"])
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
    def parse_selection_request(cls, text: str, rules: dict[str, Any] | None = None) -> dict[str, Any]:
        normalized = cls._normalize_text(text)
        normalized_rules = cls.normalize_rules(rules)
        power_classes = normalized_rules["power_classes"]
        max_targets = 6
        targets: list[dict[str, Any]] = []

        def remaining_slots() -> int:
            return max(max_targets - len(targets), 0)

        def parse_count(value: str | None) -> int:
            raw = str(value or "").strip()
            count = cls.COUNT_WORDS.get(raw)
            if count is None:
                count = int(raw) if raw.isdigit() else 1
            return max(1, min(count, max_targets))

        def add_power_targets(code: str, count: int = 1) -> None:
            for _ in range(min(count, remaining_slots())):
                targets.append(cls._target_for_power_class(code, normalized_rules))

        alias_to_code = {
            alias: code
            for code, aliases in cls.POWER_CLASS_ALIASES.items()
            for alias in aliases
        }
        alias_pattern = "|".join(sorted((re.escape(alias) for alias in alias_to_code), key=len, reverse=True))
        count_value_pattern = rf"[1-6]|{'|'.join(cls.COUNT_WORDS)}"
        power_code_pattern = "|".join(sorted((re.escape(code) for code in power_classes), key=len, reverse=True))
        compact_separator_pattern = r"x|х|\*"
        token_pattern = re.compile(
            rf"(?:(?P<count>\b\d{{1,2}}\b|{'|'.join(cls.COUNT_WORDS)})\s+)?(?P<alias>{alias_pattern})\b"
            rf"|(?<!\w)(?P<compact_count>{count_value_pattern})\s*(?:{compact_separator_pattern}|шт\.?|штук[аи]?)\s*(?P<compact_code>{power_code_pattern})(?!\w)"
            rf"|(?<!\w)(?P<reverse_code>{power_code_pattern})\s*(?:{compact_separator_pattern})\s*(?P<reverse_count>{count_value_pattern})(?!\w)"
            rf"|(?<!\w)(?P<word_count>{count_value_pattern})\s+(?P<compact_word_code>{power_code_pattern})(?!\w)"
            r"|(?P<number>\b\d{1,3}\b)\s*(?P<unit>м2|м²|кв\.?|квадрат(?:ов|а)?|квадратный метр(?:ов|а)?)?",
            re.IGNORECASE,
        )

        for match in token_pattern.finditer(normalized):
            alias = match.group("alias")
            if alias:
                count = parse_count(match.group("count"))
                code = alias_to_code[alias]
                add_power_targets(code, count)
            elif match.group("compact_code") or match.group("compact_word_code"):
                code = cls._normalize_power_code(match.group("compact_code") or match.group("compact_word_code"), normalized_rules)
                if code:
                    add_power_targets(code, parse_count(match.group("compact_count") or match.group("word_count")))
            elif match.group("reverse_code"):
                code = cls._normalize_power_code(match.group("reverse_code"), normalized_rules)
                if code:
                    add_power_targets(code, parse_count(match.group("reverse_count")))
            else:
                number_raw = match.group("number")
                if not number_raw:
                    continue
                value = int(number_raw)
                unit = match.group("unit")
                power_code = cls._normalize_power_code(number_raw, normalized_rules)
                if unit:
                    if 8 <= value <= 120:
                        targets.append(cls._target_for_area(value))
                elif power_code:
                    add_power_targets(power_code)
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
    def _tiers_for_mode(cls, compressor_mode: str, rules: dict[str, Any] | None = None):
        if isinstance(rules, dict):
            tiers = rules.get("tiers")
            if not isinstance(tiers, dict):
                tiers = cls.normalize_rules(rules)["tiers"]
            if compressor_mode in tiers:
                return tiers[compressor_mode]
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
    def _sort_for_tier(products: list[dict[str, Any]], tier_key: str, sort: str | None = None) -> list[dict[str, Any]]:
        def price(product: dict[str, Any]) -> int:
            return int(product.get("price") or 0)

        sort_mode = str(sort or tier_key or "").strip().lower()
        if sort_mode in {"budget", "onoff", "price"}:
            return sorted(products, key=lambda item: (BotProductSelectionService.availability_rank(item), price(item)))
        if sort_mode == "premium":
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
        rules = await cls.get_selection_rules(session)
        parsed = cls.parse_selection_request(query, rules)
        targets = parsed["targets"]
        if not targets:
            return {"areas": [], "message": "Не нашел мощность или площадь. Напишите, например: подбор 7,7,12 или 20 и 35 м²."}

        result: dict[str, Any] = {
            "areas": [],
            "compressor_mode": parsed["compressor_mode"],
            "mode_reason": parsed["mode_reason"],
        }
        tiers = cls._tiers_for_mode(parsed["compressor_mode"], rules)
        tag_slugs = rules["default_tag_slugs"]
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
                    tag_slugs=tag_slugs,
                    limit=12,
                )
                sorted_products = [
                    product
                    for product in cls._sort_for_tier(products, tier_key, str(options.get("sort") or ""))
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
