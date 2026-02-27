import asyncio
import sys
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(".")

from core.config import settings
from models.content import GlobalConfig


DEFAULT_CONFIGS: list[tuple[str, str, str]] = [
    ("fx_rate_usd_byn", "3.4", "Курс USD/BYN для закупки"),
    ("supplier_sync_enabled", "true", "Включить авто-синк поставщиков"),
    ("supplier_sync_interval_minutes", "60", "Интервал синка поставщиков (мин)"),
    ("fx_rate_source", "manual", "Источник курса USD/BYN: manual | nbrb"),
    ("supplier_default_spreadsheet_id", "", "Spreadsheet ID по умолчанию для новых источников"),
    ("fx_supplier_markup_percent", "2.0", "Надбавка к курсу USD/BYN для закупки, %"),
]


async def run() -> None:
    db_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg")
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    created = 0
    async with async_session() as session:
        for key, value, description in DEFAULT_CONFIGS:
            existing = (
                await session.execute(select(GlobalConfig).where(GlobalConfig.key == key))
            ).scalar_one_or_none()
            if existing is not None:
                continue
            session.add(
                GlobalConfig(
                    key=key,
                    value=value,
                    description=description,
                    updated_at=datetime.now(),
                )
            )
            created += 1

        await session.commit()

    print(f"ensure_global_config_defaults: created={created}, total_keys={len(DEFAULT_CONFIGS)}")


if __name__ == "__main__":
    asyncio.run(run())
