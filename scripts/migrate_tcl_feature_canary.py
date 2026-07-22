import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(".")

from core.config import settings
from services.tcl_feature_canary_service import (
    TclFeatureCanaryService,
    load_tcl_feature_canary_manifest,
)


DEFAULT_MANIFEST = Path("data/feature_canary/tcl_2026.json")


async def run(*, manifest_path: Path, execute: bool, output: Path | None) -> dict:
    manifest = load_tcl_feature_canary_manifest(manifest_path)
    engine = create_async_engine(settings.DATABASE_URL)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            report = await TclFeatureCanaryService(session, manifest).run(execute=execute)
            if execute:
                await session.commit()
            else:
                await session.rollback()
    finally:
        await engine.dispose()
    rendered = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if output:
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Canary migration of TCL 2026 catalog Features")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--execute", action="store_true", help="Commit reviewed changes")
    parser.add_argument("--output", type=Path, help="Write the JSON report to this path")
    args = parser.parse_args()
    asyncio.run(run(manifest_path=args.manifest, execute=args.execute, output=args.output))


if __name__ == "__main__":
    main()
