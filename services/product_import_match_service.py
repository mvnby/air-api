from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Product


def source_url_variants(raw: str | None) -> list[str]:
    value = str(raw or "").strip()
    if not value:
        return []
    variants = [value]
    if value.endswith("/"):
        variants.append(value.rstrip("/"))
    elif value.startswith("http"):
        variants.append(f"{value}/")
    return list(dict.fromkeys(variants))


def model_tokens_from_specs(specs: dict) -> tuple[str, str]:
    indoor = str(
        specs.get("model_indoor")
        or specs.get("Модель внутреннего блока")
        or ""
    ).strip()
    outdoor = str(
        specs.get("model_outdoor")
        or specs.get("Модель наружного блока")
        or ""
    ).strip()
    return indoor, outdoor


def candidate_matches_models(product: Product, *, indoor: str, outdoor: str) -> bool:
    product_specs = product.specs or {}
    if not isinstance(product_specs, dict):
        product_specs = {}

    candidate_indoor, candidate_outdoor = model_tokens_from_specs(product_specs)
    title = (product.title or "").lower()

    if indoor and outdoor:
        return (
            indoor.lower() in title
            and outdoor.lower() in title
        ) or (
            candidate_indoor.lower() == indoor.lower()
            and candidate_outdoor.lower() == outdoor.lower()
        )

    if indoor and not outdoor:
        has_indoor = indoor.lower() in title or candidate_indoor.lower() == indoor.lower()
        has_no_outdoor = not candidate_outdoor and "/" not in title
        return has_indoor and has_no_outdoor

    if outdoor and not indoor:
        has_outdoor = outdoor.lower() in title or candidate_outdoor.lower() == outdoor.lower()
        has_no_indoor = not candidate_indoor
        return has_outdoor and has_no_indoor

    return False


async def find_existing_product_for_import(
    session: AsyncSession,
    *,
    source_url: str,
    normalized_specs: dict,
    update_existing: bool,
) -> Product | None:
    for variant in source_url_variants(source_url):
        existing = (
            await session.execute(select(Product).where(Product.source_url == variant))
        ).scalar_one_or_none()
        if existing:
            return existing

    if not update_existing:
        return None

    indoor, outdoor = model_tokens_from_specs(normalized_specs)
    probe = indoor or outdoor
    if not probe:
        return None

    candidates = (
        await session.execute(
            select(Product)
            .where(Product.title.ilike(f"%{probe}%"))
            .limit(20)
        )
    ).scalars().all()
    for candidate in candidates:
        if candidate_matches_models(candidate, indoor=indoor, outdoor=outdoor):
            return candidate
    return None
