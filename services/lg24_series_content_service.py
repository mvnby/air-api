"""Seed LG series content from lg24.by product/category pages."""

from __future__ import annotations

import re
from typing import Any, Iterable, Sequence

import httpx
from bs4 import BeautifulSoup, Tag
from slugify import slugify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Brand, BrandFeature, ProductSeries, ProductSeriesFeatureLink
from parsers.lg24 import Lg24Parser
from services.catalog_revision_service import CatalogRevisionService
from services.lg24_series_content_data import BRAND_FEATURE_SEEDS, SERIES_SEEDS, Lg24SeriesSeed


def normalize_seed_slug(value: str) -> str:
    return slugify(value or "", lowercase=True)


def clean_text(value: Any) -> str:
    text = str(value or "").replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    text = text.replace("СМОТРЕТЬ ВИДЕО ЦЕЛИКОМ", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def text_matches_series(series: ProductSeries, seed: Lg24SeriesSeed) -> bool:
    current = {
        normalize_seed_slug(series.slug or ""),
        normalize_seed_slug(series.title or ""),
    }
    candidates = {normalize_seed_slug(seed.title), *(normalize_seed_slug(item) for item in seed.match_slugs)}
    return bool(current & candidates)


def image_url_from_tag(img: Tag, current_url: str) -> str:
    raw = img.get("data-large_image") or img.get("data-src") or img.get("src") or ""
    url = Lg24Parser._to_abs_url(str(raw), current_url)
    if not url or url.startswith("data:"):
        return ""
    return url


def extract_short_features(soup: BeautifulSoup) -> list[str]:
    container = soup.select_one(".woocommerce-product-details__short-description")
    if not container:
        return []

    items: list[str] = []
    seen: set[str] = set()
    for li in container.select("li"):
        text = clean_text(li.get_text(" ", strip=True))
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        items.append(text)
    return items


def extract_feature_blocks(soup: BeautifulSoup, *, max_blocks: int = 8) -> list[dict[str, str | None]]:
    blocks: list[dict[str, str | None]] = []
    started = False
    excluded_titles = {"габаритные размеры", "отзывы", "добавить отзыв отменить ответ"}

    for heading in soup.find_all(["h2", "h3"]):
        title = clean_text(heading.get_text(" ", strip=True))
        title_key = title.casefold()
        if heading.name == "h2":
            if "преимущества" in title_key:
                started = True
                continue
            if started:
                break
        if not started or heading.name != "h3" or not title:
            continue
        if title_key in excluded_titles:
            continue
        if "отзыв" in title_key:
            continue

        text = ""
        parent = heading.parent if isinstance(heading.parent, Tag) else heading
        for sibling in parent.find_next_siblings():
            if not isinstance(sibling, Tag):
                continue
            if sibling.find(["h2", "h3"]):
                break
            sibling_text = clean_text(sibling.get_text(" ", strip=True))
            if sibling_text:
                text = sibling_text
                break

        blocks.append(
            {
                "title": title,
                "text": text or None,
                "image_url": None,
                "icon": None,
                "footnote": None,
            }
        )
        if len(blocks) >= max_blocks:
            break
    return blocks


def extract_feature_gallery_images(soup: BeautifulSoup, current_url: str, *, limit: int = 8) -> list[str]:
    images: list[str] = []
    seen: set[str] = set()
    started = False

    for node in soup.find_all(["h2", "h3", "img"]):
        if node.name in {"h2", "h3"}:
            text = clean_text(node.get_text(" ", strip=True)).casefold()
            if node.name == "h2" and "преимущества" in text:
                started = True
                continue
            if node.name == "h2" and started:
                break
        if not started or node.name != "img":
            continue
        url = image_url_from_tag(node, current_url)
        if not url or url in seen:
            continue
        seen.add(url)
        images.append(url)
        if len(images) >= limit:
            break
    return images


def detected_feature_slugs(text_chunks: Sequence[str]) -> list[str]:
    haystack = " ".join(clean_text(chunk) for chunk in text_chunks if chunk).casefold()
    slugs: list[str] = []
    for feature in BRAND_FEATURE_SEEDS:
        if any(keyword.casefold() in haystack for keyword in feature.keywords):
            slugs.append(feature.slug)
    return slugs


async def fetch_series_page_content(client: httpx.AsyncClient, seed: Lg24SeriesSeed) -> tuple[list[str], list[dict[str, str | None]], list[str], str]:
    parser = Lg24Parser()
    source_url = seed.source_url
    if Lg24Parser._is_category_url(source_url):
        urls = await parser.get_import_urls(source_url)
        source_url = urls[0] if urls else source_url

    response = await client.get(source_url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    return (
        extract_short_features(soup),
        extract_feature_blocks(soup),
        extract_feature_gallery_images(soup, str(response.url)),
        str(response.url),
    )


async def upsert_brand_features(
    session: AsyncSession,
    *,
    brand_id: int,
    execute: bool,
    overwrite: bool,
) -> dict[str, int]:
    existing = (
        await session.execute(select(BrandFeature).where(BrandFeature.brand_id == brand_id))
    ).scalars().all()
    by_slug = {feature.slug: feature for feature in existing}
    ids: dict[str, int] = {}

    for index, seed in enumerate(BRAND_FEATURE_SEEDS):
        feature = by_slug.get(seed.slug)
        if feature is None:
            if not execute:
                continue
            feature = BrandFeature(
                brand_id=brand_id,
                slug=seed.slug,
                title=seed.title,
                text=seed.text,
                icon=seed.icon,
                aliases=list(seed.aliases),
                sort_order=(index + 1) * 10,
                is_published=True,
            )
            session.add(feature)
            await session.flush()
        elif overwrite:
            feature.title = seed.title
            feature.text = seed.text
            feature.icon = seed.icon
            feature.aliases = list(seed.aliases)
            feature.sort_order = (index + 1) * 10
            session.add(feature)

        if feature.id is not None:
            ids[seed.slug] = int(feature.id)

    return ids


async def sync_series_feature_links(
    session: AsyncSession,
    *,
    series: ProductSeries,
    feature_ids: Iterable[int],
    execute: bool,
) -> int:
    normalized = [int(value) for value in dict.fromkeys(feature_ids) if value]
    if not normalized or series.id is None:
        return 0

    existing = (
        await session.execute(
            select(ProductSeriesFeatureLink).where(ProductSeriesFeatureLink.series_id == series.id)
        )
    ).scalars().all()
    existing_ids = {int(link.feature_id) for link in existing}
    to_add = [feature_id for feature_id in normalized if feature_id not in existing_ids]
    if not execute:
        return len(to_add)

    base_order = max((int(link.sort_order or 0) for link in existing), default=0)
    for offset, feature_id in enumerate(to_add, start=1):
        session.add(
            ProductSeriesFeatureLink(
                series_id=int(series.id),
                feature_id=feature_id,
                sort_order=base_order + offset * 10,
            )
        )
    return len(to_add)


def should_update_value(current: Any, *, overwrite: bool) -> bool:
    if overwrite:
        return True
    if current is None:
        return True
    if isinstance(current, str):
        return not current.strip()
    if isinstance(current, list):
        return not current
    return False


async def seed_lg24_series_content(
    session: AsyncSession,
    *,
    execute: bool = False,
    overwrite: bool = False,
    seeds: Iterable[Lg24SeriesSeed] = SERIES_SEEDS,
) -> dict[str, Any]:
    brand = (await session.execute(select(Brand).where(Brand.slug == "lg"))).scalar_one_or_none()
    if brand is None or brand.id is None:
        return {"updated": 0, "linked": 0, "missed": ["LG brand not found"]}

    series_rows = (
        await session.execute(select(ProductSeries).where(ProductSeries.brand_id == brand.id))
    ).scalars().all()
    feature_ids = await upsert_brand_features(
        session,
        brand_id=int(brand.id),
        execute=execute,
        overwrite=overwrite,
    )

    updated = 0
    linked = 0
    missed: list[str] = []
    kept: list[str] = []
    applied: list[str] = []

    async with httpx.AsyncClient(
        headers=Lg24Parser._HEADERS,
        follow_redirects=True,
        timeout=20.0,
    ) as client:
        for seed in seeds:
            matched = [series for series in series_rows if text_matches_series(series, seed)]
            if not matched:
                missed.append(seed.title)
                continue

            short_features, feature_blocks, gallery_images, resolved_source_url = await fetch_series_page_content(client, seed)
            features = short_features or list(seed.fallback_features)
            block_text = [
                str(value)
                for block in feature_blocks
                for value in (block.get("title"), block.get("text"))
                if value
            ]
            detected_slugs = detected_feature_slugs([*features, *block_text, seed.title, seed.description])
            detected_ids = [feature_ids[slug] for slug in detected_slugs if slug in feature_ids]

            for series in matched:
                changed = False
                if should_update_value(series.tagline, overwrite=overwrite):
                    series.tagline = seed.tagline
                    changed = True
                if should_update_value(series.short_description, overwrite=overwrite):
                    series.short_description = seed.short_description
                    changed = True
                if should_update_value(series.description, overwrite=overwrite):
                    series.description = seed.description
                    changed = True
                if should_update_value(series.source_url, overwrite=overwrite):
                    series.source_url = seed.source_url
                    changed = True
                if should_update_value(series.features, overwrite=overwrite):
                    series.features = list(features)
                    changed = True
                if feature_blocks and should_update_value(series.feature_blocks, overwrite=overwrite):
                    series.feature_blocks = feature_blocks
                    changed = True
                if gallery_images and should_update_value(series.gallery_images, overwrite=overwrite):
                    series.gallery_images = gallery_images
                    changed = True

                linked += await sync_series_feature_links(
                    session,
                    series=series,
                    feature_ids=detected_ids,
                    execute=execute,
                )

                if changed:
                    applied.append(f"{series.title} <- {seed.title} ({resolved_source_url})")
                    updated += 1
                    if execute:
                        session.add(series)
                else:
                    kept.append(series.title)

    if execute and (updated or linked):
        await CatalogRevisionService.bump_commit_and_purge(
            session,
            scope="lg24_series_content_seed",
            brand_slugs=["lg"],
        )
    elif execute:
        await session.commit()
    else:
        await session.rollback()

    return {
        "updated": updated,
        "linked": linked,
        "missed": missed,
        "kept": kept,
        "applied": applied,
        "mode": "execute" if execute else "dry-run",
    }
