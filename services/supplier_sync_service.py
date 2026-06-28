from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from crud.supplier import SupplierDAO, SupplierOfferDAO, SupplierSourceDAO, SupplierSyncRunDAO
from models.supplier import SupplierOffer, SupplierPriceSource
from services.supplier_availability import parse_qty_with_text_fallback
from services.google_service import get_google_service
from services.supplier_match_service import supplier_offer_match_payload


def _col_to_idx(col: str) -> int:
    token = (col or "").strip().upper()
    if not token:
        return -1
    if not token.isalpha():
        return -1
    n = 0
    for ch in token:
        if "A" <= ch <= "Z":
            n = n * 26 + (ord(ch) - ord("A") + 1)
        else:
            return -1
    return n - 1 if n > 0 else -1


def _get_cell(row: list[str], col: str, range_start_col_idx: int = 0) -> str:
    idx = _col_to_idx(col)
    if idx >= 0:
        idx -= max(0, range_start_col_idx)
    if idx < 0 or idx >= len(row):
        return ""
    return str(row[idx]).strip()


def _parse_decimal(raw: str) -> Optional[Decimal]:
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


def _parse_qty(raw: str) -> int:
    number = _parse_decimal(raw)
    if number is not None:
        try:
            return int(number)
        except Exception:
            return 0
    return parse_qty_with_text_fallback(raw)


def _normalize_currency(raw: str) -> str:
    value = (raw or "").strip().upper()
    if not value:
        return "USD"
    if "USD" in value or "$" in value:
        return "USD"
    if value in {"BYN", "BYR", "РУБ", "RUB", "Р"}:
        return "BYN"
    if "EUR" in value or "€" in value:
        return "EUR"
    return value


def _extract_range_start_row(range_a1: Optional[str]) -> int:
    value = (range_a1 or "").strip()
    if not value:
        return 1
    # Supports "A14:E29" and "Sheet1!A14:E29"
    m = re.search(r"([A-Za-z]+)(\d+)\s*:\s*([A-Za-z]+)(\d+)", value)
    if m:
        try:
            return max(1, int(m.group(2)))
        except ValueError:
            return 1
    return 1


def _extract_range_start_col_idx(range_a1: Optional[str]) -> int:
    value = (range_a1 or "").strip()
    if not value:
        return 0
    # Supports "C6:K65" and "Sheet1!C6:K65"
    m = re.search(r"([A-Za-z]+)(\d+)\s*:\s*([A-Za-z]+)(\d+)", value)
    if not m:
        return 0
    return max(0, _col_to_idx(m.group(1)))


class SupplierSyncService:
    @staticmethod
    async def sync_source(
        session: AsyncSession,
        source: SupplierPriceSource,
    ) -> dict:
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
            if not supplier or not supplier.spreadsheet_id:
                raise ValueError("Supplier spreadsheet is not configured")

            spreadsheet_id = supplier.spreadsheet_id
            sheet_name = source.sheet_name
            range_a1 = source.range_a1
            await session.commit()

            values = get_google_service().read_sheet_values(
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
                range_a1=range_a1,
            )

            # Do not hard-skip first row; rely on logical row validation instead.
            data_rows = values
            rows_total = len(data_rows)
            range_start_row = _extract_range_start_row(source.range_a1)
            range_start_col_idx = _extract_range_start_col_idx(source.range_a1)

            for idx, row in enumerate(data_rows):
                title_raw = _get_cell(row, source.col_title, range_start_col_idx)
                qty_raw = _get_cell(row, source.col_qty, range_start_col_idx)
                wholesale_raw = _get_cell(row, source.col_wholesale, range_start_col_idx)
                rrc_raw = _get_cell(row, source.col_rrc_byn, range_start_col_idx)
                ext_id = _get_cell(row, source.col_external_id, range_start_col_idx)
                wholesale_value = _parse_decimal(wholesale_raw)
                rrc_value = _parse_decimal(rrc_raw)

                # Skip non-product rows (headers/series text rows):
                # if either wholesale or RRC is empty/non-numeric.
                if wholesale_value is None or rrc_value is None:
                    rows_skipped += 1
                    continue

                # external_id is optional in UI: fallback to title, then to sheet row number
                if not ext_id:
                    ext_id = title_raw
                if not ext_id:
                    sheet_row_num = range_start_row + idx
                    ext_id = f"row-{sheet_row_num}"
                if ext_id in seen_ids:
                    sheet_row_num = range_start_row + idx
                    ext_id = f"{ext_id}__r{sheet_row_num}"
                seen_ids.add(ext_id)

                currency_token = (source.col_wholesale_currency or "").strip().upper()
                if currency_token in {"BYN", "USD", "EUR"}:
                    wholesale_currency = currency_token
                elif currency_token:
                    wholesale_currency = _normalize_currency(_get_cell(row, currency_token, range_start_col_idx))
                else:
                    wholesale_currency = "USD"

                offer_payload = {
                    "supplier_id": source.supplier_id,
                    "source_id": source.id,
                    "external_id": ext_id,
                    "title_raw": title_raw or None,
                    **supplier_offer_match_payload(title_raw),
                    "qty_raw": qty_raw or None,
                    "wholesale_raw": wholesale_raw or None,
                    "rrc_raw": rrc_raw or None,
                    "qty": _parse_qty(qty_raw),
                    "wholesale_value": wholesale_value,
                    "wholesale_currency": wholesale_currency,
                    "rrc_byn": rrc_value,
                    "is_active": True,
                    "last_seen_at": datetime.now(),
                }
                await SupplierOfferDAO.upsert_offer(session, offer_payload)
                rows_upserted += 1

            active_sources = await SupplierSourceDAO.list_active_google_sources(session)
            active_for_supplier = [s for s in active_sources if s.supplier_id == source.supplier_id]
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

    @staticmethod
    async def sync_source_by_id(session: AsyncSession, source_id: int) -> dict:
        source = await SupplierSourceDAO.get_source(session, source_id)
        if not source:
            raise ValueError("Supplier source not found")
        return await SupplierSyncService.sync_source(session, source)

    @staticmethod
    async def sync_all_active_sources(session: AsyncSession) -> list[dict]:
        sources = await SupplierSourceDAO.list_active_google_sources(session)
        results: list[dict] = []
        for source in sources:
            result = await SupplierSyncService.sync_source(session, source)
            results.append(result)
        return results
