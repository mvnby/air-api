import argparse
import asyncio
import sys

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(".")

from core.config import settings
from services.lg24_series_content_service import seed_lg24_series_content


async def run_seed(*, execute: bool, overwrite: bool, import_media: bool) -> None:
    db_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg")
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        result = await seed_lg24_series_content(
            session,
            execute=execute,
            overwrite=overwrite,
            import_media=import_media,
        )

    await engine.dispose()

    print(f"[{result['mode'].upper()}] updated={result['updated']} linked={result['linked']} missed={len(result['missed'])}")
    media = result.get("media") or {}
    if media.get("enabled"):
        print(
            "[media] "
            f"planned={media.get('planned', 0)} "
            f"imported={media.get('imported', 0)} "
            f"reused={media.get('reused', 0)} "
            f"failed={len(media.get('failed') or [])}"
        )
        for item in media.get("failed") or []:
            print(f"[media-failed] {item.get('url')}: {item.get('error')}")
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
    parser.add_argument(
        "--import-media",
        action="store_true",
        help="Download LG24 promo images into the media library and store local URLs",
    )
    args = parser.parse_args()
    asyncio.run(run_seed(execute=args.execute, overwrite=args.overwrite, import_media=args.import_media))


if __name__ == "__main__":
    main()
