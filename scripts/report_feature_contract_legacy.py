"""Print a deterministic, read-only inventory of legacy Feature data."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(".")

from core.config import settings
from services.feature_contract_legacy_report_service import FeatureContractLegacyReportService


async def run(sample_limit: int) -> None:
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as session:
            report = await FeatureContractLegacyReportService.build(
                session,
                sample_limit=sample_limit,
            )
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-limit", type=int, default=25)
    args = parser.parse_args()
    asyncio.run(run(args.sample_limit))


if __name__ == "__main__":
    main()
