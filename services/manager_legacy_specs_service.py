"""Service-layer helpers for one-off legacy specs normalization."""

import ast
import json
from typing import Any

from core.logger import logger
from models import Product
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select


LEGACY_TO_SYSTEM_MAP = {
    "Тип кондиционера": "type",
    "Дата выхода на рынок": "release_year",
    "Тип внутреннего блока": "indoor_type",
    "Режим работы": "modes",
    "Цвет": "color",
    "Wi-Fi": "wifi_ready",
    "Инверторная технология": "inverter",
    "Внутренний блок": "_delete_",
    "Наружный блок": "_delete_",
    "Пульт дистанционного управления": "_delete_",
    "Мощность охлаждения": "capacity_cooling_kw",
    "Мощность обогрева": "capacity_heating_kw",
    "Обслуживаемая площадь": "area_m2",
    "Потребляемая мощность при охлаждении": "power_cons_cooling_kw",
    "Потребляемая мощность при обогреве": "power_cons_heating_kw",
    "Энергоэффективность при охлаждении (EER)": "eer",
    "Энергоэффективность при обогреве (COP)": "cop",
    "Максимальный расход воздуха внутреннего блока": "airflow_max",
    "Максимальная длина магистрали": "pipe_max_length",
    "Перепад высот": "pipe_max_height",
    "Хладагент (фреон)": "freon_type",
    "Рабочая температура при охлаждении": "temp_range_cool",
    "Рабочая температура при обогреве": "temp_range_heat",
    "Шум внутреннего блока": "noise_indoor",
    "Шум наружного блока": "noise_outdoor",
    "Ширина внутреннего блока": "width_indoor",
    "Высота внутреннего блока": "height_indoor",
    "Глубина внутреннего блока": "depth_indoor",
    "Ширина наружного блока": "width_outdoor",
    "Высота наружного блока": "height_outdoor",
    "Глубина наружного блока": "depth_outdoor",
    "Вес внутреннего блока": "weight_indoor",
    "Вес наружного блока": "weight_outdoor",
    "Модель внутреннего блока": "model_indoor",
    "Модель наружного блока": "model_outdoor",
}


def _clean_legacy_value(value: Any) -> Any:
    if isinstance(value, str):
        value_lower = value.lower().strip()
        if value_lower == "да":
            return True
        if value_lower == "нет":
            return False
    return value


class ManagerLegacySpecsService:
    @staticmethod
    async def normalize_legacy_specs(
        session: AsyncSession,
        *,
        dry_run: bool = True,
    ) -> dict:
        stmt = select(Product).where(Product.specs != None)
        result = await session.execute(stmt)
        products = result.scalars().all()

        updated_count = 0
        preview_log = []

        for product in products:
            try:
                old_specs = product.specs
                if old_specs is None:
                    continue

                if isinstance(old_specs, str):
                    try:
                        old_specs = json.loads(old_specs)
                    except json.JSONDecodeError:
                        try:
                            old_specs = ast.literal_eval(old_specs)
                        except (ValueError, SyntaxError):
                            logger.warning(f"Product {product.id} has invalid format: {old_specs}")
                            continue

                if not isinstance(old_specs, dict):
                    continue

                new_specs = {}
                changed = False
                for old_key, value in old_specs.items():
                    new_key = LEGACY_TO_SYSTEM_MAP.get(old_key, old_key)
                    if new_key == "_delete_":
                        changed = True
                        continue

                    new_value = _clean_legacy_value(value)
                    if new_key != old_key or new_value != value:
                        changed = True

                    new_specs[new_key] = new_value

                if changed:
                    if not dry_run:
                        product.specs = new_specs
                        session.add(product)
                    updated_count += 1
                    if len(preview_log) < 5:
                        preview_log.append(
                            {
                                "id": product.id,
                                "before_sample": list(old_specs.keys())[:2],
                                "after_sample": list(new_specs.keys())[:2],
                            }
                        )
            except Exception as exc:
                logger.error(f"Error normalizing product {product.id}: {exc}")
                continue

        if not dry_run:
            await session.commit()

        return {
            "message": "Normalization complete",
            "dry_run": dry_run,
            "products_processed": len(products),
            "products_updated": updated_count,
            "sample_changes": preview_log,
        }
