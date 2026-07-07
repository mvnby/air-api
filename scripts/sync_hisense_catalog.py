from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from decimal import Decimal
import sys
from typing import Any

sys.path.append(".")

from parsers.hisense_catalog import HisenseCatalogParser
from services.hisense_price_service import (
    HISENSE_PRICE_SHEET_NAME,
    HISENSE_PRICE_SOURCE_TYPE,
    HISENSE_SPREADSHEET_ID,
    HISENSE_SPREADSHEET_URL,
    load_hisense_price_offers,
)


def _source_payload(supplier_id: int) -> dict[str, Any]:
    return {
        "supplier_id": supplier_id,
        "source_type": HISENSE_PRICE_SOURCE_TYPE,
        "spreadsheet_id": HISENSE_SPREADSHEET_ID,
        "sheet_name": HISENSE_PRICE_SHEET_NAME,
        "range_a1": None,
        "city_bucket": "minsk",
        "header_row_index": 4,
        "col_external_id": "A",
        "col_title": "A",
        "col_wholesale": "K",
        "col_wholesale_currency": "BYN",
        "col_rrc_byn": "I",
        "col_qty": "L",
        "col_source_url": None,
        "is_active": True,
    }


async def ensure_supplier_source(*, execute: bool) -> tuple[int | None, int | None]:
    from sqlalchemy import select

    from core.database import async_session_maker
    from models import Supplier, SupplierPriceSource

    async with async_session_maker() as session:
        supplier = (
            await session.execute(select(Supplier).where(Supplier.code == "hisense"))
        ).scalar_one_or_none()
        if supplier is None:
            print("+ supplier hisense")
            if not execute:
                return None, None
            supplier = Supplier(
                name="Hisense",
                code="hisense",
                is_active=True,
                priority=95,
                spreadsheet_id=HISENSE_SPREADSHEET_ID,
                spreadsheet_url=HISENSE_SPREADSHEET_URL,
            )
            session.add(supplier)
            await session.commit()
            await session.refresh(supplier)
        else:
            changes = {}
            if supplier.spreadsheet_id != HISENSE_SPREADSHEET_ID:
                changes["spreadsheet_id"] = HISENSE_SPREADSHEET_ID
            if supplier.spreadsheet_url != HISENSE_SPREADSHEET_URL:
                changes["spreadsheet_url"] = HISENSE_SPREADSHEET_URL
            if changes:
                print(f"~ supplier hisense {changes}")
                if execute:
                    for key, value in changes.items():
                        setattr(supplier, key, value)
                    supplier.updated_at = datetime.now()
                    session.add(supplier)
                    await session.commit()
                    await session.refresh(supplier)
            else:
                print(f"= supplier hisense id={supplier.id}")

        if supplier.id is None:
            return None, None

        source = (
            await session.execute(
                select(SupplierPriceSource).where(
                    SupplierPriceSource.supplier_id == supplier.id,
                    SupplierPriceSource.sheet_name == HISENSE_PRICE_SHEET_NAME,
                )
            )
        ).scalar_one_or_none()
        payload = _source_payload(int(supplier.id))
        if source is None:
            print(f"+ source {HISENSE_PRICE_SHEET_NAME}")
            if not execute:
                return int(supplier.id), None
            source = SupplierPriceSource(**payload)
            session.add(source)
            await session.commit()
            await session.refresh(source)
        else:
            changes = {key: value for key, value in payload.items() if getattr(source, key) != value}
            if changes:
                print(f"~ source {source.id} {changes}")
                if execute:
                    for key, value in changes.items():
                        setattr(source, key, value)
                    source.updated_at = datetime.now()
                    session.add(source)
                    await session.commit()
                    await session.refresh(source)
            else:
                print(f"= source {source.id} {HISENSE_PRICE_SHEET_NAME}")

        return int(supplier.id), int(source.id) if source and source.id else None


async def sync_source(source_id: int) -> dict[str, Any]:
    from core.database import async_session_maker
    from models import SupplierPriceSource
    from services.supplier_sync_service import SupplierSyncService

    async with async_session_maker() as session:
        source = await session.get(SupplierPriceSource, source_id)
        if source is None:
            raise RuntimeError(f"Source {source_id} was not found")
        return await SupplierSyncService.sync_source(session, source)


async def list_active_offers(source_id: int, *, limit: int | None) -> list[Any]:
    from sqlalchemy import select

    from core.database import async_session_maker
    from models import SupplierOffer

    async with async_session_maker() as session:
        stmt = (
            select(SupplierOffer)
            .where(
                SupplierOffer.source_id == source_id,
                SupplierOffer.is_active.is_(True),
                SupplierOffer.source_url.is_not(None),
                SupplierOffer.source_url != "",
            )
            .order_by(SupplierOffer.external_id.asc())
        )
        if limit:
            stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def import_and_map_offer(offer: Any, *, overwrite_series: bool) -> tuple[int, str]:
    from sqlalchemy import select

    from core.database import async_session_maker
    from models import Product, ProductSupplierMapping
    from services.importer_service import ImporterService

    if not offer.source_url:
        raise RuntimeError(f"Offer {offer.external_id} has no source URL")

    result = await ImporterService().import_product(offer.source_url, update_existing=True)
    product = result["product"]
    product_id = int(product.id)
    async with async_session_maker() as session:
        db_product = await session.get(Product, product_id)
        if db_product is None:
            raise RuntimeError(f"Imported product {product_id} was not found")
        if offer.rrc_byn is not None and offer.rrc_byn > Decimal("0"):
            db_product.price = int(offer.rrc_byn)
            session.add(db_product)

        mapping = (
            await session.execute(
                select(ProductSupplierMapping).where(
                    ProductSupplierMapping.supplier_id == offer.supplier_id,
                    ProductSupplierMapping.external_id == offer.external_id,
                )
            )
        ).scalar_one_or_none()
        if mapping is None:
            mapping = ProductSupplierMapping(
                product_id=product_id,
                supplier_id=offer.supplier_id,
                external_id=offer.external_id,
                is_active=True,
                mapped_by="hisense_catalog_import",
            )
        else:
            mapping.product_id = product_id
            mapping.is_active = True
            mapping.mapped_by = "hisense_catalog_import"
            mapping.mapped_at = datetime.now()
        session.add(mapping)
        await session.commit()

    await update_series_content(offer.source_url, overwrite=overwrite_series)
    return product_id, offer.external_id


async def update_series_content(source_url: str, *, overwrite: bool) -> None:
    from sqlalchemy import select

    from core.database import async_session_maker
    from models import Brand, ProductSeries

    parser = HisenseCatalogParser()
    payload = await parser.parse_series_content(source_url)
    title = str(payload.get("title") or "").strip()
    if not title:
        return
    async with async_session_maker() as session:
        brand = (await session.execute(select(Brand).where(Brand.slug == "hisense"))).scalar_one_or_none()
        if brand is None or brand.id is None:
            return
        series = (
            await session.execute(
                select(ProductSeries).where(
                    ProductSeries.brand_id == brand.id,
                    ProductSeries.title == title,
                )
            )
        ).scalar_one_or_none()
        if series is None:
            return

        def should_update(value: Any) -> bool:
            return overwrite or value in (None, "", [], {})

        if should_update(series.source_url):
            series.source_url = payload.get("source_url")
        if should_update(series.description):
            series.description = payload.get("description")
        if should_update(series.short_description):
            description = str(payload.get("description") or "")
            series.short_description = description[:260] if description else None
        if should_update(series.hero_image):
            series.hero_image = payload.get("hero_image")
        if should_update(series.gallery_images):
            series.gallery_images = payload.get("gallery_images") or []
        if should_update(series.features):
            series.features = payload.get("features") or []
        series.is_published = True
        session.add(series)
        await session.commit()


async def main_async(args: argparse.Namespace) -> None:
    offers_preview = await load_hisense_price_offers()
    urls_count = len({offer.series_url for offer in offers_preview if offer.series_url})
    with_url = sum(1 for offer in offers_preview if offer.source_url)
    print(f"Hisense price preview: offers={len(offers_preview)}, with_urls={with_url}, series_urls={urls_count}")

    if not args.execute:
        print("Dry run only. Re-run with --execute to apply supplier/source changes.")
        return

    supplier_id, source_id = await ensure_supplier_source(execute=args.execute)
    if source_id is None:
        raise RuntimeError("Hisense source was not created")

    if args.sync:
        print(f"* sync source {source_id}")
        print(await sync_source(source_id))

    if args.import_products:
        offers = await list_active_offers(source_id, limit=args.limit)
        print(f"* import products: {len(offers)} offer(s)")
        for index, offer in enumerate(offers, start=1):
            try:
                product_id, external_id = await import_and_map_offer(offer, overwrite_series=args.overwrite_series)
                print(f"  {index}/{len(offers)} ok product={product_id} offer={external_id}")
            except Exception as exc:
                print(f"  {index}/{len(offers)} error offer={offer.external_id}: {exc}")

    print(f"Done. supplier_id={supplier_id}, source_id={source_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Hisense catalog and supplier price sheet")
    parser.add_argument("--execute", action="store_true", help="Create/update supplier source")
    parser.add_argument("--sync", action="store_true", help="Sync supplier offers from XLSX")
    parser.add_argument("--import-products", action="store_true", help="Import products from source URLs and map offers")
    parser.add_argument("--limit", type=int, default=None, help="Limit imported offers")
    parser.add_argument("--overwrite-series", action="store_true", help="Overwrite existing series content fields")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
