from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from crud.supplier import ProductLocalStockDAO, SupplierMappingDAO
from models.supplier import SupplierOffer, SupplierPriceSource
from services.fx_rate_service import FxRateService
from services.supplier_availability import classify_availability


class ProductSupplyMetricsService:
    @staticmethod
    async def compute_for_products(
        session: AsyncSession,
        products: list[Any],
    ) -> dict[int, dict[str, Any]]:
        product_ids = [int(p.id) for p in products if getattr(p, "id", None)]
        if not product_ids:
            return {}

        fx_rate = await FxRateService.get_supplier_usd_byn_rate(session)

        mappings = await SupplierMappingDAO.list_mappings_for_products(session, product_ids)
        if not mappings:
            local_stock_rows = await ProductLocalStockDAO.list_for_products(session, product_ids)
            vitebsk_map = {row.product_id: int(row.qty or 0) for row in local_stock_rows}
            return {
                pid: {
                    "min_cost_byn": None,
                    "recommended_price_byn": None,
                    "margin_abs_preview": None,
                    "margin_pct_preview": None,
                    "vitebsk_qty": vitebsk_map.get(pid, 0),
                    "minsk_qty": 0,
                    "availability_status": "in_stock_now" if vitebsk_map.get(pid, 0) > 0 else "out_of_stock",
                }
                for pid in product_ids
            }

        keys = {(m.supplier_id, m.external_id) for m in mappings}
        offers_res = await session.execute(
            select(SupplierOffer).where(
                SupplierOffer.is_active.is_(True),
                SupplierOffer.supplier_id.in_([k[0] for k in keys]),
            )
        )
        offers = [
            o for o in offers_res.scalars().all() if (o.supplier_id, o.external_id) in keys
        ]
        offer_map = {(o.supplier_id, o.external_id): o for o in offers}

        source_res = await session.execute(
            select(SupplierPriceSource).where(SupplierPriceSource.is_active.is_(True))
        )
        sources = source_res.scalars().all()
        supplier_city = {}
        for source in sources:
            supplier_city[source.supplier_id] = source.city_bucket or "minsk"

        local_stock_rows = await ProductLocalStockDAO.list_for_products(session, product_ids)
        vitebsk_map = {row.product_id: int(row.qty or 0) for row in local_stock_rows}

        metrics: dict[int, dict[str, Any]] = {}
        price_map = {int(p.id): int(p.price or 0) for p in products}
        for pid in product_ids:
            metrics[pid] = {
                "min_cost_byn": None,
                "min_cost_byn_fallback": None,
                "recommended_price_byn": None,
                "margin_abs_preview": None,
                "margin_pct_preview": None,
                "vitebsk_qty": vitebsk_map.get(pid, 0),
                "minsk_qty": 0,
                "minsk_incoming": False,
                "availability_status": "out_of_stock",
            }

        for mapping in mappings:
            offer = offer_map.get((mapping.supplier_id, mapping.external_id))
            if not offer:
                continue
            slot = metrics[int(mapping.product_id)]

            if (
                fx_rate
                and offer.wholesale_value is not None
                and (offer.wholesale_currency or "").upper() == "USD"
            ):
                cost_byn = float((offer.wholesale_value * fx_rate).quantize(Decimal("0.01")))
                if offer.qty > 0:
                    if slot["min_cost_byn"] is None or cost_byn < slot["min_cost_byn"]:
                        slot["min_cost_byn"] = cost_byn
                if slot["min_cost_byn_fallback"] is None or cost_byn < slot["min_cost_byn_fallback"]:
                    slot["min_cost_byn_fallback"] = cost_byn

            if offer.rrc_byn is not None:
                rrc = float(offer.rrc_byn)
                if slot["recommended_price_byn"] is None or rrc < slot["recommended_price_byn"]:
                    slot["recommended_price_byn"] = rrc

            city_bucket = supplier_city.get(mapping.supplier_id, "minsk")
            if city_bucket == "minsk":
                slot["minsk_qty"] += int(offer.qty or 0)
                if classify_availability(offer.qty_raw) == "incoming":
                    slot["minsk_incoming"] = True

        for pid, slot in metrics.items():
            if slot["min_cost_byn"] is None:
                slot["min_cost_byn"] = slot["min_cost_byn_fallback"]
            slot.pop("min_cost_byn_fallback", None)
            site_price = float(price_map.get(pid, 0))
            min_cost = slot["min_cost_byn"]
            if min_cost is not None and site_price > 0:
                margin_abs = round(site_price - min_cost, 2)
                slot["margin_abs_preview"] = margin_abs
                slot["margin_pct_preview"] = round(margin_abs / site_price, 4)

            if slot["vitebsk_qty"] > 0:
                slot["availability_status"] = "in_stock_now"
            elif slot["minsk_qty"] > 0 or slot["minsk_incoming"]:
                slot["availability_status"] = "available_2_3_days"
            else:
                slot["availability_status"] = "out_of_stock"

        return metrics
