from dataclasses import dataclass
from typing import Any

from models import Product


HOME_ALLOWED_PRODUCT_KINDS = {"complete_split_system"}
YANDEX_BUSINESS_PLACEMENT = ("yandex_business", "categories")


@dataclass(frozen=True)
class ProductEligibilityResult:
    reason_codes: tuple[str, ...]
    reasons: tuple[str, ...]

    @property
    def is_eligible(self) -> bool:
        return not self.reason_codes


class ProductCollectionEligibility:
    @staticmethod
    def evaluate(
        product: Product,
        *,
        surface_key: str,
        slot_key: str,
        supply_metrics: dict[str, Any],
        price_override: int | None = None,
    ) -> ProductEligibilityResult:
        failures: list[tuple[str, str]] = []
        if not product.is_published:
            failures.append(("not_published", "Товар снят с публикации."))
        if not str(product.slug or "").strip():
            failures.append(("missing_public_url", "У товара нет стабильного публичного URL."))
        if (
            surface_key == "home"
            and slot_key == "featured_products"
            and product.product_kind not in HOME_ALLOWED_PRODUCT_KINDS
        ):
            failures.append(
                (
                    "unsupported_product_kind",
                    "Для главной разрешены только готовые бытовые сплит-системы.",
                )
            )
        public_price = product.price if price_override is None else price_override
        if int(public_price or 0) <= 0:
            failures.append(("missing_price", "Не задана корректная публичная цена."))
        if (surface_key, slot_key) != YANDEX_BUSINESS_PLACEMENT:
            if not str(product.main_image or "").strip():
                failures.append(("missing_main_image", "Не задано основное изображение."))
            specs = product.specs or {}
            if not specs.get("area_m2"):
                failures.append(
                    (
                        "missing_card_specs",
                        "Не заполнена каноническая площадь для товарной карточки.",
                    )
                )
            if not supply_metrics.get("availability_status"):
                failures.append(
                    (
                        "missing_availability",
                        "Не удалось определить нормализованный статус доступности.",
                    )
                )
        return ProductEligibilityResult(
            reason_codes=tuple(code for code, _ in failures),
            reasons=tuple(message for _, message in failures),
        )
