from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from crud.supplier import SupplierDAO, SupplierOfferDAO, SupplierSourceDAO, SupplierSyncRunDAO
from models.supplier import SupplierPriceSource
from services.supplier_availability import parse_qty_with_text_fallback
from services.supplier_match_service import supplier_offer_match_payload
from services.supplier_source_url import normalize_source_url
from services.xlsx_reader import XlsxCell, XlsxSheet, read_xlsx_sheet


HISENSE_PRICE_SOURCE_TYPE = "hisense_price_xlsx"
HISENSE_SPREADSHEET_ID = "1iYDMAYKTS_niuNtRXDO-N26H2KH5Hq-CnmUmiMQlrFc"
HISENSE_SPREADSHEET_URL = (
    f"https://docs.google.com/spreadsheets/d/{HISENSE_SPREADSHEET_ID}/edit?gid=401022608#gid=401022608"
)
HISENSE_PRICE_SHEET_NAME = "КРАТКИЙ ПРАЙС СПЛИТЫ"


@dataclass(frozen=True)
class HisensePriceOffer:
    external_id: str
    title_raw: str
    model: str
    series_title: str | None
    series_url: str | None
    source_url: str | None
    qty_raw: str | None
    wholesale_raw: str | None
    rrc_raw: str | None
    qty: int
    wholesale_value: Decimal | None
    rrc_byn: Decimal | None
    sheet_row: int


async def download_hisense_price_xlsx(spreadsheet_id: str = HISENSE_SPREADSHEET_ID) -> bytes:
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=xlsx"
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=30.0,
        headers={"User-Agent": "Mozilla/5.0 (Codex Hisense Sync)"},
        verify=False,
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content


def parse_hisense_price_sheet(sheet: XlsxSheet) -> list[HisensePriceOffer]:
    offers: list[HisensePriceOffer] = []
    seen_external_ids: set[str] = set()
    current_series_title: str | None = None
    current_series_url: str | None = None

    for row_idx, row in enumerate(sheet.rows, start=1):
        model = _cell_text(row, 0)
        if not model:
            continue

        linked_url = _first_supported_hyperlink(row)
        rrc_raw = _cell_text(row, 8)
        dealer_raw = _cell_text(row, 9)
        special_raw = _cell_text(row, 10)
        qty_raw = _cell_text(row, 11)
        rrc_value = _parse_decimal(rrc_raw)
        dealer_value = _parse_decimal(dealer_raw)
        special_value = _parse_decimal(special_raw)
        wholesale_value = special_value if special_value is not None else dealer_value
        wholesale_raw = special_raw if special_value is not None else dealer_raw

        if linked_url and (rrc_value is None and wholesale_value is None):
            current_series_title = model
            current_series_url = normalize_source_url(linked_url)
            continue

        if rrc_value is None and wholesale_value is None:
            continue

        external_id = model
        if external_id in seen_external_ids:
            external_id = f"{external_id}__r{row_idx}"
        seen_external_ids.add(external_id)

        source_url = append_model_fragment(current_series_url, model) if current_series_url else None
        title_parts = ["Hisense", model]
        if current_series_title:
            title_parts.append(current_series_title)
        offers.append(
            HisensePriceOffer(
                external_id=external_id,
                title_raw=" · ".join(title_parts),
                model=model,
                series_title=current_series_title,
                series_url=current_series_url,
                source_url=source_url,
                qty_raw=qty_raw or None,
                wholesale_raw=wholesale_raw or None,
                rrc_raw=rrc_raw or None,
                qty=_parse_qty(qty_raw),
                wholesale_value=wholesale_value,
                rrc_byn=rrc_value,
                sheet_row=row_idx,
            )
        )

    return offers


async def load_hisense_price_offers(
    *,
    spreadsheet_id: str = HISENSE_SPREADSHEET_ID,
    sheet_name: str = HISENSE_PRICE_SHEET_NAME,
) -> list[HisensePriceOffer]:
    content = await download_hisense_price_xlsx(spreadsheet_id)
    sheet = read_xlsx_sheet(content, sheet_name)
    return parse_hisense_price_sheet(sheet)


async def sync_hisense_price_source(
    session: AsyncSession,
    source: SupplierPriceSource,
) -> dict[str, Any]:
    run = await SupplierSyncRunDAO.create_run(session, source.id)
    rows_total = 0
    rows_upserted = 0
    rows_skipped = 0
    rows_deactivated = 0
    seen_ids: set[str] = set()
    status = "success"
    error_message = None

    try:
        supplier = await SupplierDAO.get_supplier(session, source.supplier_id)
        spreadsheet_id = source.spreadsheet_id or (supplier.spreadsheet_id if supplier else None)
        if not spreadsheet_id:
            raise ValueError("Hisense spreadsheet is not configured")

        sheet_name = source.sheet_name or HISENSE_PRICE_SHEET_NAME
        await session.commit()
        offers = await load_hisense_price_offers(spreadsheet_id=spreadsheet_id, sheet_name=sheet_name)
        rows_total = len(offers)

        for offer in offers:
            if not offer.wholesale_value or not offer.rrc_byn:
                rows_skipped += 1
                continue
            seen_ids.add(offer.external_id)
            payload = {
                "supplier_id": source.supplier_id,
                "source_id": source.id,
                "external_id": offer.external_id,
                "title_raw": offer.title_raw,
                **supplier_offer_match_payload(offer.title_raw),
                "source_url": offer.source_url,
                "qty_raw": offer.qty_raw,
                "wholesale_raw": offer.wholesale_raw,
                "rrc_raw": offer.rrc_raw,
                "qty": offer.qty,
                "wholesale_value": offer.wholesale_value,
                "wholesale_currency": "BYN",
                "rrc_byn": offer.rrc_byn,
                "is_active": True,
                "last_seen_at": datetime.now(),
            }
            await SupplierOfferDAO.upsert_offer(session, payload)
            rows_upserted += 1

        active_sources = await SupplierSourceDAO.list_active_sync_sources(session)
        active_for_supplier = [item for item in active_sources if item.supplier_id == source.supplier_id]
        if len(active_for_supplier) <= 1:
            rows_deactivated = await SupplierOfferDAO.deactivate_missing_offers(
                session=session,
                supplier_id=source.supplier_id,
                present_external_ids=seen_ids,
            )

        source.last_sync_at = datetime.now()
        source.last_sync_status = "success"
        source.last_sync_error = None
        source.updated_at = datetime.now()
        session.add(source)
        await session.commit()
    except Exception as exc:
        status = "error"
        error_message = str(exc)
        source.last_sync_at = datetime.now()
        source.last_sync_status = "error"
        source.last_sync_error = error_message[:500]
        source.updated_at = datetime.now()
        session.add(source)
        await session.commit()

    run = await SupplierSyncRunDAO.finish_run(
        session,
        run,
        status=status,
        rows_total=rows_total,
        rows_upserted=rows_upserted,
        rows_skipped=rows_skipped,
        rows_deactivated=rows_deactivated,
        error=error_message,
    )
    return {
        "run_id": run.id,
        "source_id": run.source_id,
        "status": run.status,
        "rows_total": run.rows_total,
        "rows_upserted": run.rows_upserted,
        "rows_skipped": run.rows_skipped,
        "rows_deactivated": run.rows_deactivated,
        "error": run.error,
    }


def append_model_fragment(url: str | None, model: str) -> str | None:
    normalized = normalize_source_url(url)
    if not normalized:
        return None
    parts = urlsplit(normalized)
    fragment = f"model={quote(model.strip(), safe='')}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, fragment))


def _cell_text(row: list[XlsxCell], idx: int) -> str:
    if idx < 0 or idx >= len(row):
        return ""
    return str(row[idx].value or "").replace("\xa0", " ").strip()


def _first_supported_hyperlink(row: list[XlsxCell]) -> str | None:
    for cell in row:
        link = normalize_source_url(cell.hyperlink)
        if link and ("hisense-air.ru/product/" in link or "breez.ru/products/" in link):
            return link
    return None


def _parse_decimal(raw: str | None) -> Decimal | None:
    value = (raw or "").replace("\xa0", " ").strip()
    if not value:
        return None
    value = value.replace(" ", "").replace(",", ".")
    cleaned = "".join(ch for ch in value if ch.isdigit() or ch in ".-").strip(".")
    if cleaned.count(".") > 1:
        whole, fractional = cleaned.rsplit(".", 1)
        cleaned = f"{whole.replace('.', '')}.{fractional}"
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _parse_qty(raw: str | None) -> int:
    number = _parse_decimal(raw)
    if number is not None:
        try:
            return int(number)
        except Exception:
            return 0
    return parse_qty_with_text_fallback(raw or "")
