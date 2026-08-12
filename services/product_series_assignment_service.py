"""Canonical Product -> ProductSeries assignment and legacy specs mirroring."""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from models import Product, ProductSeries, Tag
from services.brand_series_service import (
    SERIES_SPEC_KEYS,
    extract_series_name,
    ensure_series,
)


SERIES_ID_UNSET = object()
_SERIES_SPEC_KEY_LOOKUP = {key.strip().casefold() for key in SERIES_SPEC_KEYS}


class ProductSeriesAssignmentError(ValueError):
    def __init__(self, message: str, *, field_errors: dict[str, str]) -> None:
        super().__init__(message)
        self.field_errors = field_errors


def _mirror_series_in_specs(
    specs: Optional[Dict[str, Any]],
    *,
    series_title: Optional[str],
) -> tuple[Dict[str, Any], bool]:
    current = dict(specs or {})
    mirrored = {
        key: value
        for key, value in current.items()
        if str(key).strip().casefold() not in _SERIES_SPEC_KEY_LOOKUP
    }
    typed_specs = current.get("__typed_specs")
    if isinstance(typed_specs, dict):
        mirrored_typed_specs = dict(typed_specs)
        mirrored_typed_specs.pop("series", None)
        if series_title:
            mirrored_typed_specs["series"] = {
                "type": "text",
                "raw": series_title,
                "value": series_title,
            }
        if mirrored_typed_specs:
            mirrored["__typed_specs"] = mirrored_typed_specs
        else:
            mirrored.pop("__typed_specs", None)
    if series_title:
        mirrored["series"] = series_title
    return mirrored, mirrored != current


class ProductSeriesAssignmentService:
    @staticmethod
    async def validate_update_request(
        session: AsyncSession,
        *,
        product: Product,
        requested_brand_id: object,
        explicit_brand_override: bool,
        requested_series_id: object,
        explicit_series_override: bool,
    ) -> None:
        final_brand_id = (
            requested_brand_id if explicit_brand_override else product.brand_id
        )
        if explicit_series_override:
            if requested_series_id is None:
                return
            series = await session.get(ProductSeries, int(requested_series_id))
            if series is None:
                message = "Выбранная серия не найдена."
                raise ProductSeriesAssignmentError(
                    message,
                    field_errors={"series_id": message},
                )
            if series.brand_id != final_brand_id:
                message = "Выбранная серия не принадлежит итоговому бренду товара."
                raise ProductSeriesAssignmentError(
                    message,
                    field_errors={"series_id": message, "brand_id": message},
                )
            return

        if explicit_brand_override and product.series_id is not None:
            series = await session.get(ProductSeries, product.series_id)
            if series is not None and series.brand_id != final_brand_id:
                message = "Сначала выберите серию нового бренда или очистите серию товара."
                raise ProductSeriesAssignmentError(
                    message,
                    field_errors={"brand_id": message, "series_id": message},
                )

    @staticmethod
    async def assign(
        session: AsyncSession,
        *,
        product: Product,
        requested_series_id: object = SERIES_ID_UNSET,
        specs: Optional[Dict[str, Any]] = None,
        title: Optional[str] = None,
        tags: Optional[Sequence[Tag]] = None,
        group_slug_by_id: Optional[Dict[int, str]] = None,
        brand_name: Optional[str] = None,
        original_brand_id: Optional[int] = None,
        explicit_brand_override: bool = False,
        allow_series_tag_fallback: bool = True,
        allow_series_title_fallback: bool = True,
        clear_series_when_missing: bool = False,
        change_kinds: Optional[set[str]] = None,
    ) -> bool:
        data_specs = specs if specs is not None else (product.specs or {})
        changed = False

        if requested_series_id is not SERIES_ID_UNSET:
            if requested_series_id is None:
                if product.series_id is not None:
                    product.series_id = None
                    changed = True
                if product.series_assignment_source != "manual":
                    product.series_assignment_source = "manual"
                    changed = True
                mirrored, specs_changed = _mirror_series_in_specs(
                    data_specs,
                    series_title=None,
                )
                if specs_changed or product.specs != mirrored:
                    product.specs = mirrored
                    changed = True
                if changed:
                    session.add(product)
                return changed

            series = await session.get(ProductSeries, int(requested_series_id))
            if series is None:
                message = "Выбранная серия не найдена."
                raise ProductSeriesAssignmentError(
                    message,
                    field_errors={"series_id": message},
                )
            if series.brand_id != product.brand_id:
                message = "Выбранная серия не принадлежит итоговому бренду товара."
                raise ProductSeriesAssignmentError(
                    message,
                    field_errors={"series_id": message, "brand_id": message},
                )

            if product.series_id != series.id:
                product.series_id = series.id
                changed = True
            if product.series_assignment_source != "manual":
                product.series_assignment_source = "manual"
                changed = True
            mirrored, specs_changed = _mirror_series_in_specs(
                data_specs,
                series_title=series.title,
            )
            if specs_changed or product.specs != mirrored:
                product.specs = mirrored
                changed = True
            if changed:
                session.add(product)
            return changed

        current_series = (
            await session.get(ProductSeries, product.series_id)
            if product.series_id is not None
            else None
        )
        if (
            explicit_brand_override
            and original_brand_id != product.brand_id
            and current_series is not None
            and current_series.brand_id != product.brand_id
        ):
            message = "Сначала выберите серию нового бренда или очистите серию товара."
            raise ProductSeriesAssignmentError(
                message,
                field_errors={"brand_id": message, "series_id": message},
            )

        if product.series_assignment_source == "manual":
            mirrored, specs_changed = _mirror_series_in_specs(
                data_specs,
                series_title=current_series.title if current_series else None,
            )
            if specs_changed or product.specs != mirrored:
                product.specs = mirrored
                session.add(product)
                return True
            return False

        series_name = extract_series_name(
            specs=data_specs,
            tags=list(tags or []) if allow_series_tag_fallback else [],
            group_slug_by_id=group_slug_by_id or {},
            title=(title if title is not None else product.title or "")
            if allow_series_title_fallback
            else "",
            brand_name=brand_name if allow_series_title_fallback else None,
        )
        if series_name:
            series, series_changed = await ensure_series(
                session,
                title=series_name,
                brand_id=product.brand_id,
            )
            if series_changed and change_kinds is not None:
                change_kinds.add("taxonomy")
            changed = changed or series_changed
            if product.series_id != series.id:
                product.series_id = series.id
                changed = True
            if product.series_assignment_source != "derived":
                product.series_assignment_source = "derived"
                changed = True
            mirrored, specs_changed = _mirror_series_in_specs(
                data_specs,
                series_title=series.title,
            )
            if specs_changed or product.specs != mirrored:
                product.specs = mirrored
                changed = True
        elif clear_series_when_missing:
            if product.series_id is not None:
                product.series_id = None
                changed = True
            if product.series_assignment_source != "derived":
                product.series_assignment_source = "derived"
                changed = True
            mirrored, specs_changed = _mirror_series_in_specs(
                data_specs,
                series_title=None,
            )
            if specs_changed or product.specs != mirrored:
                product.specs = mirrored
                changed = True
        elif current_series is not None:
            mirrored, specs_changed = _mirror_series_in_specs(
                data_specs,
                series_title=current_series.title,
            )
            if specs_changed or product.specs != mirrored:
                product.specs = mirrored
                changed = True

        if changed:
            session.add(product)
        return changed
