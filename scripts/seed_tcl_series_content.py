import argparse
import asyncio
import sys
from dataclasses import dataclass
from typing import Iterable

from slugify import slugify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(".")

from core.config import settings
from models import Brand, ProductSeries
from services.catalog_revision_service import CatalogRevisionService


@dataclass(frozen=True)
class SeriesSeed:
    title: str
    match_slugs: tuple[str, ...]
    description: str
    features: tuple[str, ...]


TCL_SERIES: tuple[SeriesSeed, ...] = (
    SeriesSeed(
        title="FreshIN 3.0",
        match_slugs=("freshin-3-0", "freshin3-0", "freshin", "fci"),
        description=(
            "Флагманская инверторная серия TCL с подачей свежего воздуха FreshIN+, "
            "фильтрами QuadriPuri, индикатором качества воздуха и тихим ночным режимом."
        ),
        features=(
            "Подача свежего воздуха FreshIN+",
            "Фильтры QuadriPuri",
            "Индикатор качества воздуха",
            "Голосовое управление",
            "Gentle Breeze",
            "Самоочистка внутреннего и наружного блоков",
            "Wi-Fi управление TCL Home",
        ),
    ),
    SeriesSeed(
        title="X-Fresh",
        match_slugs=("x-fresh", "xfresh", "fai"),
        description=(
            "Инверторная серия с притоком свежего воздуха до 60 м3/ч, высокой "
            "энергоэффективностью и отдельным режимом вентиляции без охлаждения или обогрева."
        ),
        features=(
            "Подача свежего воздуха Fresh Air",
            "Режим вентиляции без охлаждения",
            "Умное энергосбережение T-AI",
            "Дежурный обогрев 8 °C",
            "Самоочистка",
            "Wi-Fi управление",
        ),
    ),
    SeriesSeed(
        title="SaveIN AI",
        match_slugs=("savein-ai", "save-in-ai", "zg11", "zg41"),
        description=(
            "Серия TCL SaveIN AI делает упор на экономичную инверторную работу, "
            "мягкое распределение воздуха и удобное управление для квартиры или дома."
        ),
        features=(
            "Умное энергосбережение",
            "Gentle Breeze",
            "Smart Inverter",
            "Самоочистка",
            "Режим ECO",
            "Wi-Fi управление",
        ),
    ),
    SeriesSeed(
        title="BreezeIN 2.0",
        match_slugs=("breezein-2-0", "breeze-in-2-0", "breeze-in-2-0-a", "ug11v3ah"),
        description=(
            "Инверторная серия BreezeIN 2.0 подходит для ежедневного охлаждения и обогрева: "
            "мягкий поток воздуха, самоочистка и стабильная работа в широком диапазоне температур."
        ),
        features=(
            "Gentle Breeze",
            "Smart Airflow",
            "Самоочистка",
            "Режим ECO",
            "Wi-Fi управление",
            "Обогрев в холодное межсезонье",
        ),
    ),
    SeriesSeed(
        title="BreezeIN 1.0",
        match_slugs=("breezein-1-0", "breeze-in-1-0", "breeze-in-1-0-a", "tph11ihb"),
        description=(
            "Базовая инверторная линейка BreezeIN для спокойного бытового использования: "
            "охлаждение, обогрев, осушение и понятный набор повседневных функций."
        ),
        features=(
            "Smart Inverter",
            "Режим ECO",
            "3D Airflow",
            "Режим сна",
            "Функция I FEEL",
            "Самодиагностика",
        ),
    ),
    SeriesSeed(
        title="Ocarina",
        match_slugs=("ocarina", "ocarina-t-pro-c-paneliu-tpg21", "tpg21", "tpg21i3ahb"),
        description=(
            "Дизайнерская инверторная серия TCL с расширенными функциями комфорта, "
            "очистки воздуха и автоматического распределения потока."
        ),
        features=(
            "Умное энергосбережение",
            "Gentle Breeze",
            "УФ-лампа и биполярный ионизатор",
            "Самоочистка",
            "Smart Airflow",
            "Wi-Fi управление",
        ),
    ),
    SeriesSeed(
        title="Elite Inverter",
        match_slugs=(
            "elite-inverter",
            "elite-invertor",
            "elite-inverter-c-paneliu-xa71n",
            "xa71if",
            "xa71in",
            "xa71n",
        ),
        description=(
            "Практичная инверторная серия TCL Elite для помещений, где нужны базовая "
            "надежность, экономичная работа компрессора и понятное управление."
        ),
        features=(
            "Smart Inverter",
            "Режим ECO",
            "3D Airflow",
            "Режим сна",
            "Функция I FEEL",
            "Wi-Fi управление опционально",
        ),
    ),
    SeriesSeed(
        title="SaveIN",
        match_slugs=("savein", "save-in", "zg31"),
        description=(
            "Доступная серия TCL On/Off для базового охлаждения и обогрева без лишней "
            "сложности, с привычными режимами для дома и небольшого офиса."
        ),
        features=(
            "Режим ECO",
            "Режим сна",
            "Осушение",
            "Таймер 24 ч",
            "Самодиагностика",
            "Авторестарт",
        ),
    ),
    SeriesSeed(
        title="Elite",
        match_slugs=("elite", "elite-on", "xab1"),
        description=(
            "Базовая серия TCL On/Off: простой кондиционер для стандартных задач "
            "охлаждения, обогрева и осушения в квартире или офисе."
        ),
        features=(
            "8 режимов подачи воздуха вверх-вниз",
            "3D Airflow",
            "Осушение",
            "Таймер 24 ч",
            "Самодиагностика",
            "Wi-Fi управление опционально",
        ),
    ),
)


def _norm(value: str) -> str:
    return slugify(value or "", lowercase=True)


def _matches(series: ProductSeries, seed: SeriesSeed) -> bool:
    current = {_norm(series.slug), _norm(series.title)}
    candidates = {_norm(seed.title), *(_norm(item) for item in seed.match_slugs)}
    return bool(current & candidates)


def _needs_update(series: ProductSeries, seed: SeriesSeed, *, overwrite: bool) -> bool:
    if overwrite:
        return True
    return not (series.description or "").strip() or not list(series.features or [])


async def seed_tcl_series(
    *,
    execute: bool,
    overwrite: bool,
    seeds: Iterable[SeriesSeed] = TCL_SERIES,
) -> None:
    db_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg")
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        brand = (
            await session.execute(select(Brand).where(Brand.slug == "tcl"))
        ).scalar_one_or_none()
        if brand is None:
            print("[skip] TCL brand not found")
            await engine.dispose()
            return

        series_rows = (
            await session.execute(select(ProductSeries).where(ProductSeries.brand_id == brand.id))
        ).scalars().all()

        updated = 0
        missed: list[str] = []
        for seed in seeds:
            matched = [item for item in series_rows if _matches(item, seed)]
            if not matched:
                missed.append(seed.title)
                continue

            for series in matched:
                if not _needs_update(series, seed, overwrite=overwrite):
                    print(f"[keep] {series.title} ({series.slug}) already has content")
                    continue
                series.description = seed.description
                series.features = list(seed.features)
                session.add(series)
                updated += 1
                print(f"[update] {series.title} ({series.slug}) <- {seed.title}")

        if updated and execute:
            await CatalogRevisionService.bump_commit_and_purge(
                session,
                scope="tcl_series_content_seed",
                brand_slugs=[brand.slug],
            )

        if execute:
            await session.commit()
        else:
            await session.rollback()

    await engine.dispose()
    mode = "APPLY" if execute else "DRY-RUN"
    print(f"[{mode}] updated={updated}, missed={len(missed)}")
    if missed:
        print("[missed] " + ", ".join(missed))


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed TCL product series descriptions and features")
    parser.add_argument("--execute", action="store_true", help="Commit changes")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing descriptions/features")
    args = parser.parse_args()
    asyncio.run(seed_tcl_series(execute=args.execute, overwrite=args.overwrite))


if __name__ == "__main__":
    main()
