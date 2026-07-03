from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import sys
from typing import Any

from sqlalchemy import select

sys.path.append(".")

from core.database import async_session_maker
from models.supplier import Supplier, SupplierPriceSource
from services.supplier_sync_service import SupplierSyncService


@dataclass(frozen=True)
class SourceConfig:
    sheet_name: str
    range_a1: str
    col_external_id: str
    col_title: str
    col_wholesale: str
    col_wholesale_currency: str
    col_rrc_byn: str
    col_qty: str

    def payload(self, supplier_id: int) -> dict[str, Any]:
        return {
            "supplier_id": supplier_id,
            "source_type": "google_sheet",
            "sheet_name": self.sheet_name,
            "range_a1": self.range_a1,
            "city_bucket": "minsk",
            "header_row_index": 1,
            "col_external_id": self.col_external_id,
            "col_title": self.col_title,
            "col_wholesale": self.col_wholesale,
            "col_wholesale_currency": self.col_wholesale_currency,
            "col_rrc_byn": self.col_rrc_byn,
            "col_qty": self.col_qty,
            "col_source_url": None,
            "is_active": True,
        }


BIOCOND_MDV_SOURCES = (
    SourceConfig(
        sheet_name="MDV RAC",
        range_a1="C3:H123",
        col_external_id="C",
        col_title="C",
        col_wholesale="F",
        col_wholesale_currency="USD",
        col_rrc_byn="G",
        col_qty="H",
    ),
    SourceConfig(
        sheet_name="MDV PAC",
        range_a1="A1:F250",
        col_external_id="B",
        col_title="B",
        col_wholesale="D",
        col_wholesale_currency="USD",
        col_rrc_byn="E",
        col_qty="F",
    ),
)


def _diff(existing: SupplierPriceSource, payload: dict[str, Any]) -> dict[str, tuple[Any, Any]]:
    changes: dict[str, tuple[Any, Any]] = {}
    for key, value in payload.items():
        if getattr(existing, key) != value:
            changes[key] = (getattr(existing, key), value)
    return changes


async def ensure_sources(*, execute: bool, sync: bool) -> None:
    async with async_session_maker() as session:
        supplier = (
            await session.execute(select(Supplier).where(Supplier.code == "biokond"))
        ).scalar_one_or_none()
        if supplier is None or supplier.id is None:
            raise SystemExit("Supplier with code 'biokond' was not found")

        for config in BIOCOND_MDV_SOURCES:
            payload = config.payload(int(supplier.id))
            source = (
                await session.execute(
                    select(SupplierPriceSource).where(
                        SupplierPriceSource.supplier_id == supplier.id,
                        SupplierPriceSource.sheet_name == config.sheet_name,
                    )
                )
            ).scalar_one_or_none()

            if source is None:
                print(f"+ create source {config.sheet_name}: {payload}")
                if execute:
                    source = SupplierPriceSource(**payload)
                    session.add(source)
                    await session.commit()
                    await session.refresh(source)
            else:
                changes = _diff(source, payload)
                if changes:
                    print(f"~ update source {source.id} {config.sheet_name}: {changes}")
                    if execute:
                        for key, value in payload.items():
                            setattr(source, key, value)
                        session.add(source)
                        await session.commit()
                        await session.refresh(source)
                else:
                    print(f"= source {source.id} {config.sheet_name}: already configured")

            if execute and sync and source is not None and source.id is not None:
                result = await SupplierSyncService.sync_source(session, source)
                print(f"* sync {config.sheet_name}: {result}")

        if not execute:
            print("Dry run only. Re-run with --execute to apply changes.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ensure Biocond MDV supplier price sources")
    parser.add_argument("--execute", action="store_true", help="Apply source changes")
    parser.add_argument("--sync", action="store_true", help="Sync configured sources after applying changes")
    args = parser.parse_args()
    asyncio.run(ensure_sources(execute=args.execute, sync=args.sync))


if __name__ == "__main__":
    main()
