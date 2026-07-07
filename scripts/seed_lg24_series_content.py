import argparse
import asyncio
import sys

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(".")

from core.config import settings
from services.lg24_series_content_service import seed_lg24_series_content


async def run_seed(*, execute: bool, overwrite: bool) -> None:
    db_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg")
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        result = await seed_lg24_series_content(
            session,
            execute=execute,
            overwrite=overwrite,
        )

    await engine.dispose()

    print(f"[{result['mode'].upper()}] updated={result['updated']} linked={result['linked']} missed={len(result['missed'])}")
    for item in result["applied"]:
        print(f"[update] {item}")
    for item in result["kept"]:
        print(f"[keep] {item}")
    if result["missed"]:
        print("[missed] " + ", ".join(result["missed"]))


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed LG product series content from lg24.by")
    parser.add_argument("--execute", action="store_true", help="Commit changes")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing series content")
    args = parser.parse_args()
    asyncio.run(run_seed(execute=args.execute, overwrite=args.overwrite))


if __name__ == "__main__":
    main()
