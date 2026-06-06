import argparse
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(".")

from core.config import settings
from models import Brand


BRAND_DESCRIPTIONS: dict[str, str] = {
    "mdv": (
        "**MDV** часто смотрят, когда нужен спокойный выбор по цене и функциям: настенные модели, "
        "мульти-сплит и решения для небольших коммерческих помещений. Поможем сравнить серии по шуму, "
        "обогреву, Wi-Fi и реальным условиям монтажа."
    ),
    "tcl": (
        "**TCL** обычно выбирают для квартиры, спальни или офиса, когда хочется понятную модель без "
        "лишнего усложнения. При подборе смотрим мощность, уровень шума, наличие Wi-Fi и как наружный "
        "блок встанет на конкретном объекте."
    ),
    "chigo": (
        "**Chigo** подходит тем, кто ищет практичный кондиционер для дома или небольшого рабочего "
        "помещения. Сравним модели по площади, режиму обогрева и бюджету, чтобы не переплачивать "
        "за ненужные опции."
    ),
    "lg": (
        "**LG** чаще рассматривают для жилых комнат и офисов, где важны аккуратный внутренний блок "
        "и удобное повседневное управление. Подскажем, какие модели лучше подходят под площадь, "
        "шумовые ожидания и сценарий использования."
    ),
    "haier": (
        "**Haier** смотрят для квартир, домов и офисов, когда важны разные варианты по дизайну, "
        "мощности и набору функций. Поможем выбрать серию под помещение, место установки и требования "
        "к обогреву в межсезонье."
    ),
    "kinghome": (
        "**KINGHOME** можно рассматривать для базового охлаждения и обогрева в квартире, кабинете "
        "или небольшом магазине. При подборе сверяем площадь, запас мощности и доступность конкретной "
        "модели."
    ),
    "ultima": (
        "**Ultima** пригодится, когда нужен простой и понятный кондиционер для повседневного "
        "использования. Поможем проверить характеристики, наличие и стоимость установки до заказа."
    ),
    "energolux": (
        "**Energolux** представлен моделями для бытовых и более сложных задач: от настенных "
        "сплит-систем до полупромышленных решений. Подберем вариант по типу внутреннего блока, "
        "мощности и условиям монтажа."
    ),
}


def _normalize_key(value: str | None) -> str:
    return str(value or "").strip().lower()


def _is_empty(value: str | None) -> bool:
    return not str(value or "").strip()


async def run_backfill(*, execute: bool) -> None:
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        brands = (await session.execute(select(Brand).order_by(Brand.sort_order, Brand.title))).scalars().all()
        brands_by_key: dict[str, Brand] = {}
        for brand in brands:
            brands_by_key[_normalize_key(brand.slug)] = brand
            brands_by_key[_normalize_key(brand.title)] = brand

        updated: list[str] = []
        skipped_existing: list[str] = []
        missing: list[str] = []

        for key, description in BRAND_DESCRIPTIONS.items():
            brand = brands_by_key.get(key)
            if not brand:
                missing.append(key)
                continue

            label = f"{brand.title} ({brand.slug})"
            if not _is_empty(brand.description):
                skipped_existing.append(label)
                continue

            updated.append(label)
            if execute:
                brand.description = description
                session.add(brand)

        if execute:
            await session.commit()
        else:
            await session.rollback()

    await engine.dispose()

    mode = "APPLY" if execute else "DRY-RUN"
    action = "updated" if execute else "would_update"
    print(f"[{mode}] {action}={len(updated)}, skipped_existing={len(skipped_existing)}, missing={len(missing)}")
    if updated:
        print(f"[{mode}] {action}: {', '.join(updated)}")
    if skipped_existing:
        print(f"[{mode}] skipped existing descriptions: {', '.join(skipped_existing)}")
    if missing:
        print(f"[{mode}] configured brands not found: {', '.join(missing)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fill empty Brand.description values with short markdown intros for current brands."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Commit changes. Without this flag the script only reports what would be updated.",
    )
    args = parser.parse_args()
    asyncio.run(run_backfill(execute=args.execute))


if __name__ == "__main__":
    main()
