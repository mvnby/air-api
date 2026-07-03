from __future__ import annotations

from typing import Any

from models.supplier import SupplierPriceSource
from services.supplier_match_service import supplier_offer_match_payload
from services.supplier_source_url import extract_first_source_url, normalize_source_url
from services.supplier_sync_service import (
    _extract_range_start_col_idx,
    _extract_range_start_row,
    _get_cell,
    _parse_decimal,
)


def analyze_supplier_source_rows(
    source: SupplierPriceSource,
    values: list[list[str]],
    *,
    limit: int = 50,
) -> dict[str, Any]:
    range_start_row = _extract_range_start_row(source.range_a1)
    range_start_col_idx = _extract_range_start_col_idx(source.range_a1)
    sample_rows: list[dict[str, Any]] = []
    product_rows = 0
    section_rows = 0
    skipped_rows = 0
    url_rows = 0

    for idx, row in enumerate(values):
        row_number = range_start_row + idx
        text_cells = [str(cell or "").strip() for cell in row]
        non_empty = [cell for cell in text_cells if cell]
        if not non_empty:
            skipped_rows += 1
            if len(sample_rows) < limit:
                sample_rows.append(
                    {
                        "row_number": row_number,
                        "row_kind": "empty",
                        "notes": ["Пустая строка"],
                    }
                )
            continue

        title_raw = _get_cell(row, source.col_title, range_start_col_idx)
        external_id = _get_cell(row, source.col_external_id, range_start_col_idx)
        wholesale_raw = _get_cell(row, source.col_wholesale, range_start_col_idx)
        rrc_raw = _get_cell(row, source.col_rrc_byn, range_start_col_idx)
        qty_raw = _get_cell(row, source.col_qty, range_start_col_idx)
        source_url = _extract_configured_or_visible_url(source, row, range_start_col_idx)
        if source_url:
            url_rows += 1

        wholesale_value = _parse_decimal(wholesale_raw)
        rrc_value = _parse_decimal(rrc_raw)
        match_payload = supplier_offer_match_payload(title_raw)
        model_tokens = match_payload.get("model_tokens") or []
        notes: list[str] = []

        if wholesale_value is not None and rrc_value is not None:
            row_kind = "product"
            product_rows += 1
        elif title_raw and not model_tokens:
            row_kind = "section"
            section_rows += 1
            notes.append("Похоже на заголовок или секцию прайса")
        else:
            row_kind = "skipped"
            skipped_rows += 1
            if wholesale_value is None:
                notes.append("Оптовая цена не распознана")
            if rrc_value is None:
                notes.append("РРЦ не распознана")
            if not title_raw:
                notes.append("Название товара не найдено")

        if source_url and "onliner.by" in source_url:
            notes.append("Найдена ссылка Onliner")

        if len(sample_rows) < limit:
            sample_rows.append(
                {
                    "row_number": row_number,
                    "row_kind": row_kind,
                    "external_id": external_id or None,
                    "title_raw": title_raw or None,
                    "source_url": source_url,
                    "model_tokens": model_tokens,
                    "wholesale_raw": wholesale_raw or None,
                    "rrc_raw": rrc_raw or None,
                    "qty_raw": qty_raw or None,
                    "notes": notes,
                }
            )

    warnings: list[str] = []
    if url_rows == 0:
        warnings.append("В выбранном диапазоне не найдено видимых URL. Если ссылки скрыты как hyperlink, нужен отдельный режим чтения метаданных.")
    if product_rows == 0 and values:
        warnings.append("Не найдено строк, которые текущий sync сможет загрузить как товары.")

    return {
        "source_id": source.id,
        "rows_total": len(values),
        "product_rows": product_rows,
        "section_rows": section_rows,
        "url_rows": url_rows,
        "skipped_rows": skipped_rows,
        "sample_rows": sample_rows,
        "warnings": warnings,
    }


def _extract_configured_or_visible_url(
    source: SupplierPriceSource,
    row: list[str],
    range_start_col_idx: int,
) -> str | None:
    configured_url = normalize_source_url(_get_cell(row, source.col_source_url or "", range_start_col_idx))
    return configured_url or extract_first_source_url(row)
