from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from modules.documents.domain import (
    B2C_NATIVE_DOCUMENT_TYPES,
    ConsumerDocumentTerms,
    DEFAULT_GOODS_WARRANTY_MONTHS,
)


class ConsumerDocumentContextError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ConsumerDocumentContext:
    values: dict[str, str]
    conditions: dict[str, bool]


def build_consumer_document_context(
    *,
    document_type: str,
    terms: ConsumerDocumentTerms | None,
    seller_requisites: Mapping[str, object],
) -> ConsumerDocumentContext:
    captured_terms = terms or ConsumerDocumentTerms()
    if document_type in B2C_NATIVE_DOCUMENT_TYPES:
        required_offer_fields = {
            "offer_url": "ссылку на публичную оферту",
            "offer_version": "версию публичной оферты",
            "offer_published_on": "дату публикации оферты",
        }
        missing = [
            label
            for field, label in required_offer_fields.items()
            if not _text(seller_requisites.get(field))
        ]
        if missing:
            raise ConsumerDocumentContextError(
                "Для документа физлицу заполните " + ", ".join(missing)
            )
    goods_warranty_months = (
        _warranty_months(
            explicit=captured_terms.goods_warranty_months,
            configured=seller_requisites.get("default_goods_warranty_months"),
            fallback=DEFAULT_GOODS_WARRANTY_MONTHS,
        )
        if document_type == "b2c_supply_installation_act"
        else None
    )
    work_warranty_months = _warranty_months(
        explicit=captured_terms.work_warranty_months,
        configured=seller_requisites.get("default_work_warranty_months"),
        fallback=None,
    )
    return ConsumerDocumentContext(
        values={
            "offer.url": _text(seller_requisites.get("offer_url")),
            "offer.version": _text(seller_requisites.get("offer_version")),
            "offer.published_on": _text(seller_requisites.get("offer_published_on")),
            "equipment.brand": _text(captured_terms.equipment_brand),
            "equipment.model": _text(captured_terms.equipment_model),
            "equipment.serial": _text(captured_terms.equipment_serial),
            "equipment.display_name": _equipment_display_name(captured_terms),
            "warranty.goods.months": (
                str(goods_warranty_months) if goods_warranty_months is not None else ""
            ),
            "warranty.goods.terms": (
                _text(captured_terms.goods_warranty_terms)
                if goods_warranty_months is not None
                else ""
            ),
            "warranty.work.months": (
                str(work_warranty_months) if work_warranty_months is not None else ""
            ),
            "warranty.work.terms": _text(captured_terms.work_warranty_terms),
            "route.length_meters": _text(captured_terms.route_length_meters),
            "route.liquid_pipe_diameter_mm": _text(
                captured_terms.route_liquid_pipe_diameter_mm
            ),
            "route.gas_pipe_diameter_mm": _text(
                captured_terms.route_gas_pipe_diameter_mm
            ),
            "route.drainage": _text(captured_terms.route_drainage),
            "route.power_supply": _text(captured_terms.route_power_supply),
            "route.notes": _text(captured_terms.route_notes),
            "route.photo_fixation_status": _performed_status(
                captured_terms.route_photo_fixation_performed
            ),
            "route.pressure_test_status": _performed_status(
                captured_terms.route_pressure_test_performed
            ),
            "route.ends_capped_status": (
                "заглушены" if captured_terms.route_ends_capped else "не заглушены"
            ),
        },
        conditions={
            "warranty.goods.present": bool(goods_warranty_months),
            "warranty.work.present": bool(work_warranty_months),
            "route.photo_fixation_performed": (
                captured_terms.route_photo_fixation_performed
            ),
            "route.pressure_test_performed": (
                captured_terms.route_pressure_test_performed
            ),
            "route.ends_capped": captured_terms.route_ends_capped,
        },
    )


def _text(value: object | None) -> str:
    return str(value or "").strip()


def _equipment_display_name(terms: ConsumerDocumentTerms) -> str:
    return " ".join(
        value
        for value in (_text(terms.equipment_brand), _text(terms.equipment_model))
        if value
    )


def _warranty_months(
    *,
    explicit: int | None,
    configured: object | None,
    fallback: int | None,
) -> int | None:
    for candidate in (explicit, configured, fallback):
        if candidate is None or candidate == "":
            continue
        try:
            months = int(candidate)
        except (TypeError, ValueError):
            continue
        if 0 <= months <= 240:
            return months
    return fallback


def _performed_status(value: bool) -> str:
    return "выполнена" if value else "не выполнена"
