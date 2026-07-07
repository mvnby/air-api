"""Seed LG series content from lg24.by product/category pages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence
from urllib.parse import urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup, Tag
from slugify import slugify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Brand, BrandFeature, MediaAsset, ProductSeries, ProductSeriesFeatureLink
from parsers.lg24 import Lg24Parser
from services.catalog_revision_service import CatalogRevisionService
from services.lg24_series_content_data import BRAND_FEATURE_SEEDS, SERIES_SEEDS, Lg24SeriesSeed
from services.media_library_service import MediaLibraryService


@dataclass(frozen=True)
class ResolvedSeriesMedia:
    url: str
    created: bool


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


def normalize_remote_media_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    if not parts.scheme and not parts.netloc:
        return raw
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def first_image_url_from_tag(tag: Tag, current_url: str) -> str:
    if tag.name == "img":
        return image_url_from_tag(tag, current_url)
    for img in tag.find_all("img"):
        if not isinstance(img, Tag):
            continue
        url = image_url_from_tag(img, current_url)
        if url:
            return url
    return ""


def iter_feature_block_nodes(heading: Tag) -> Iterable[Tag]:
    for node in heading.next_elements:
        if node is heading:
            continue
        if not isinstance(node, Tag):
            continue
        if node.name in {"h2", "h3"}:
            break
        yield node


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


def extract_feature_blocks(
    soup: BeautifulSoup,
    current_url: str = "",
    *,
    max_blocks: int = 8,
) -> list[dict[str, str | None]]:
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
        image_url = ""
        for node in iter_feature_block_nodes(heading):
            if node.find(["h2", "h3"]):
                continue
            if not text and node.name in {"p", "div", "li"}:
                sibling_text = clean_text(node.get_text(" ", strip=True))
                if sibling_text:
                    text = sibling_text
            if current_url and not image_url:
                image_url = first_image_url_from_tag(node, current_url)
            if text and image_url:
                break

        blocks.append(
            {
                "title": title,
                "text": text or None,
                "image_url": image_url or None,
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
        extract_feature_blocks(soup, str(response.url)),
        extract_feature_gallery_images(soup, str(response.url)),
        str(response.url),
    )


async def resolve_or_import_series_media(
    session: AsyncSession,
    *,
    source_url: str,
    title: str,
    created_by: str | None = "lg24-series-seed",
) -> ResolvedSeriesMedia | None:
    normalized_url = normalize_remote_media_url(source_url)
    if not normalized_url:
        return None

    existing = await find_imported_series_media(session, source_url=normalized_url)
    if existing:
        return existing

    content, filename = await MediaLibraryService._download_remote_image(normalized_url)
    stored = await MediaLibraryService._store_image(content, variant_type="original")
    asset = MediaAsset(
        title=title or MediaLibraryService._title_from_filename(filename) or "LG feature",
        alt_text=title or None,
        kind="brand",
        tags=MediaLibraryService._normalize_tags(["lg", "series", "feature", "promo"]),
        variant_type="original",
        url=stored.url,
        original_url=normalized_url,
        source_filename=filename,
        mime_type=stored.mime_type,
        storage_provider=stored.storage_provider,
        processing_status="ready",
        content_hash=stored.content_hash,
        width=stored.width,
        height=stored.height,
        size_bytes=stored.size_bytes,
        created_by=created_by,
    )
    session.add(asset)
    await session.flush()
    return ResolvedSeriesMedia(url=stored.url, created=True)


async def find_imported_series_media(
    session: AsyncSession,
    *,
    source_url: str,
) -> ResolvedSeriesMedia | None:
    normalized_url = normalize_remote_media_url(source_url)
    if not normalized_url:
        return None

    existing = (
        await session.execute(
            select(MediaAsset)
            .where(MediaAsset.original_url == normalized_url)
            .order_by(MediaAsset.id.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing and existing.url:
        return ResolvedSeriesMedia(url=existing.url, created=False)
    return None


def collect_feature_block_image_urls(feature_blocks: Sequence[dict[str, Any]]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for block in feature_blocks:
        url = normalize_remote_media_url(str(block.get("image_url") or ""))
        if not url or url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


def remap_feature_block_image_urls(
    feature_blocks: Sequence[dict[str, Any]],
    media_map: dict[str, str],
) -> list[dict[str, Any]]:
    remapped: list[dict[str, Any]] = []
    for block in feature_blocks:
        next_block = dict(block)
        source_url = normalize_remote_media_url(str(next_block.get("image_url") or ""))
        if source_url and source_url in media_map:
            next_block["image_url"] = media_map[source_url]
        remapped.append(next_block)
    return remapped


async def import_series_media_urls(
    session: AsyncSession,
    *,
    urls: Sequence[str],
    execute: bool,
    title_prefix: str,
) -> dict[str, Any]:
    unique_urls = [normalize_remote_media_url(url) for url in dict.fromkeys(urls) if normalize_remote_media_url(url)]
    result: dict[str, Any] = {
        "planned": len(unique_urls),
        "imported": 0,
        "reused": 0,
        "failed": [],
        "map": {},
    }
    for index, source_url in enumerate(unique_urls, start=1):
        try:
            if execute:
                resolved = await resolve_or_import_series_media(
                    session,
                    source_url=source_url,
                    title=f"{title_prefix}: изображение {index}",
                )
            else:
                resolved = await find_imported_series_media(session, source_url=source_url)
        except Exception as exc:
            result["failed"].append({"url": source_url, "error": str(exc)})
            continue
        if not resolved:
            if not execute:
                continue
            result["failed"].append({"url": source_url, "error": "empty media url"})
            continue
        result["map"][source_url] = resolved.url
        if resolved.created:
            result["imported"] += 1
        else:
            result["reused"] += 1
    return result


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


def should_update_media_value(current: Any, next_value: Any, *, overwrite: bool, import_media: bool) -> bool:
    if should_update_value(current, overwrite=overwrite):
        return True
    return bool(import_media and next_value and current != next_value)


async def seed_lg24_series_content(
    session: AsyncSession,
    *,
    execute: bool = False,
    overwrite: bool = False,
    import_media: bool = False,
    seeds: Iterable[Lg24SeriesSeed] = SERIES_SEEDS,
) -> dict[str, Any]:
    brand = (await session.execute(select(Brand).where(Brand.slug == "lg"))).scalar_one_or_none()
    if brand is None or brand.id is None:
        return {
            "updated": 0,
            "linked": 0,
            "missed": ["LG brand not found"],
            "kept": [],
            "applied": [],
            "media": {
                "enabled": import_media,
                "planned": 0,
                "imported": 0,
                "reused": 0,
                "failed": [],
            },
            "mode": "execute" if execute else "dry-run",
        }

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
    media_planned = 0
    media_imported = 0
    media_reused = 0
    media_failed: list[dict[str, str]] = []

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
            media_map: dict[str, str] = {}
            if import_media:
                media_urls = [
                    *gallery_images,
                    *collect_feature_block_image_urls(feature_blocks),
                ]
                media_result = await import_series_media_urls(
                    session,
                    urls=media_urls,
                    execute=execute,
                    title_prefix=f"LG {seed.title}",
                )
                media_planned += int(media_result["planned"])
                media_imported += int(media_result["imported"])
                media_reused += int(media_result["reused"])
                media_failed.extend(media_result["failed"])
                media_map = media_result["map"]
                if media_map:
                    gallery_images = [
                        media_map.get(normalize_remote_media_url(url), url)
                        for url in gallery_images
                    ]
                    feature_blocks = remap_feature_block_image_urls(feature_blocks, media_map)

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
                if feature_blocks and should_update_media_value(
                    series.feature_blocks,
                    feature_blocks,
                    overwrite=overwrite,
                    import_media=import_media,
                ):
                    series.feature_blocks = feature_blocks
                    changed = True
                if gallery_images and should_update_media_value(
                    series.gallery_images,
                    gallery_images,
                    overwrite=overwrite,
                    import_media=import_media,
                ):
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
        "media": {
            "enabled": import_media,
            "planned": media_planned,
            "imported": media_imported,
            "reused": media_reused,
            "failed": media_failed,
        },
        "mode": "execute" if execute else "dry-run",
    }
