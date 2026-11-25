"""Project only eligible storefront catalog fields into the offer snapshot."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
import math
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.personal_offers import (
    PersonalOfferOptionInput,
    PersonalOfferRoomInput,
    PublicPersonalOfferInstallation,
    PublicPersonalOfferOption,
    PublicPersonalOfferResponse,
    PublicPersonalOfferRoom,
)
from models.tenancy import TenantScope
from services.catalog_decision_projection import CatalogDecisionQueryService
from services.product_collection_catalog_access import ProductCollectionCatalogAccess
from services.public_catalog_visibility_service import PublicProductProjection
from services.spec_normalizer import normalize_specs


def display_room_title(title: str | None, position: int, total: int, *, is_package: bool = False) -> str:
    if is_package:
        return (title or "").strip() or ("Комплект оборудования" if total == 1 else f"Комплект {position}")
    default = "Подбор кондиционера" if total == 1 else f"Помещение {position}"
    return (title or "").strip() or default


def _positive_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(str(value))
    except (ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _catalog_slug(value: str | None) -> str | None:
    slug = (value or "").strip()
    if not slug or slug in {".", ".."} or any(c in slug for c in "/?#%\\"):
        return None
    return slug


def _public_image(value: str | None) -> str | None:
    url = (value or "").strip()
    if not url or "\\" in url or any(ord(c) < 32 for c in url):
        return None
    if url.startswith("/media/"):
        return url
    try:
        parsed = urlsplit(url)
        if parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password:
            return url
    except ValueError:
        return None
    return None


def _wifi_state(source: Mapping[str, object], normalized: dict) -> str | None:
    value = normalized.get("wifi_state")
    if value in ("builtin", "ready"):
        return value
    # The normalizer also supplies "none" for unpopulated legacy specs.
    if value == "none" and any(
        key in source and source[key] not in (None, "")
        for key in ("wifi_state", "wifi_ready", "wifi_builtin", "wifi", "wi_fi", "wifi_module")
    ):
        return "none"
    return None


def _inverter_value(normalized_type: str | None, catalog_flag: bool) -> bool | None:
    if normalized_type == "on_off":
        return False
    if normalized_type in ("inverter", "full_dc") or catalog_flag:
        return True
    return None


def _display_option(
    option: PersonalOfferOptionInput, projection: PublicProductProjection, installation_price: Decimal | None,
) -> PublicPersonalOfferOption:
    product = projection.product
    raw_specs = product.specs if isinstance(product.specs, dict) else {}
    specs = normalize_specs(raw_specs, keep_units=False)
    inverter = specs.get("compressor_type_norm")
    original_price = Decimal(projection.price)
    price = option.price_byn
    return PublicPersonalOfferOption(
        title=product.title,
        slug=_catalog_slug(product.slug),
        main_image=_public_image(product.main_image),
        price_byn=price,
        original_price_byn=original_price if original_price > price else None,
        total_price_byn=price + installation_price if installation_price is not None else None,
        note=option.note or None,
        cooling_power_kw=_positive_number(product.power_cooling) or _positive_number(specs.get("capacity_cooling_kw")),
        noise_indoor_min_db=_positive_number(specs.get("__filter_noise_min")),
        is_inverter=_inverter_value(inverter, product.is_inverter),
        wifi=_wifi_state(raw_specs, specs),
    )


class PersonalOfferProjection:
    @staticmethod
    async def visible_products(
        session: AsyncSession, rooms: list[PersonalOfferRoomInput], scope: TenantScope,
    ) -> dict[int, PublicProductProjection]:
        product_ids = list(dict.fromkeys(option.product_id for room in rooms for option in room.options))
        visible = await ProductCollectionCatalogAccess.visible_by_ids(
            session, tenant_scope=scope, product_ids=product_ids,
        )
        if any(product_id not in visible or not visible[product_id].product.is_published for product_id in product_ids):
            raise HTTPException(409, "Одна или несколько моделей больше не доступны на этой витрине.")
        eligible = await CatalogDecisionQueryService.eligible_system_product_ids(session, product_ids)
        if eligible != set(product_ids):
            raise HTTPException(409, "В предложение можно включить только доступные комплектные сплит-системы.")
        return visible

    @staticmethod
    def build(
        rooms: list[PersonalOfferRoomInput], expires_at: datetime, products: dict[int, PublicProductProjection],
    ) -> PublicPersonalOfferResponse:
        result = []
        for position, room in enumerate(rooms, 1):
            installation = room.installation
            is_package = room.selection_mode == "package"
            equipment_total = sum((option.price_byn for option in room.options), Decimal(0)) if room.show_total else None
            total_with_installation = (
                equipment_total + installation.price_byn
                if equipment_total is not None and installation.price_byn is not None
                else None
            )
            result.append(PublicPersonalOfferRoom(
                title=display_room_title(room.title, position, len(rooms), is_package=is_package),
                selection_mode=room.selection_mode,
                equipment_total_byn=equipment_total,
                total_with_installation_byn=total_with_installation,
                installation=PublicPersonalOfferInstallation(
                    mode=installation.mode,
                    price_byn=installation.price_byn,
                    description=(installation.description or None) if installation.mode != "none" else None,
                ),
                options=[
                    _display_option(option, products[option.product_id], None if is_package else installation.price_byn)
                    for option in room.options
                ],
            ))
        return PublicPersonalOfferResponse(expires_at=expires_at, rooms=result)
