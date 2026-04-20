import logging
from decimal import Decimal
from typing import List, Optional

import slugify
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from parsers.base import BaseParser
from parsers.aircond import AircondParser
from parsers.haierproff import HaierProffParser
from parsers.hobot import HobotParser
from parsers.lg24 import Lg24Parser
from parsers.onliner import OnlinerParser
from parsers.tvoy_klimat import TvoyKlimatParser
from core.database import async_session_maker
from models import Product, ProductImage, Tag, TagGroup
from services.fx_rate_service import FxRateService
from services.import_media_service import ImportMediaService
from services.product_attachment_service import replace_manuals
from services.spec_normalizer import normalize_specs
from services.tag_logic import (
    CATEGORY_TAG_TITLES,
    detect_category_slug,
    extract_brand_name,
    extract_brand_slug,
    get_auto_tags,
)
from services.brand_series_service import sync_product_brand_series

logger = logging.getLogger(__name__)
_CATEGORY_TAG_SLUGS = {"cat-household", "cat-multi", "cat-industrial"}


def _augment_auto_slugs_with_wifi_specs(auto_slugs: List[str], specs: dict) -> List[str]:
    result = list(auto_slugs)
    normalized_specs_probe = normalize_specs(
        specs or {},
        strict_wifi_from_tags=False,
    )
    wifi_state = normalized_specs_probe.get("wifi_ready")
    if wifi_state is True and "wifi-builtin" not in result:
        result.append("wifi-builtin")
    elif wifi_state == "ready" and "wifi-ready" not in result:
        result.append("wifi-ready")
    return result


async def _normalize_import_price_to_byn(session, *, data: dict, source_url: str) -> None:
    """Convert source price to BYN if parser reports foreign currency."""
    raw_price = data.get("price")
    if raw_price is None:
        return

    currency = str(data.get("price_currency") or "BYN").strip().upper()
    if currency in {"", "BYN"}:
        return

    try:
        source_price = Decimal(str(raw_price))
    except Exception:
        logger.warning("Price conversion skipped for %s: invalid source price=%r", source_url, raw_price)
        return

    if currency != "RUB":
        logger.warning("Price conversion skipped for %s: unsupported currency=%s", source_url, currency)
        return

    rub_byn_rate = await FxRateService.get_effective_rub_byn_rate(session)
    if rub_byn_rate is None:
        logger.warning("Price conversion skipped for %s: RUB/BYN rate unavailable", source_url)
        return

    converted_price = (source_price * rub_byn_rate).quantize(Decimal("1"))
    data["price"] = int(converted_price)


async def _ensure_tag_group(
    session,
    *,
    slug: str,
    title: str,
    allow_multiple: bool = True,
    sort_order: int = 0,
) -> TagGroup:
    group = (
        await session.execute(select(TagGroup).where(TagGroup.slug == slug))
    ).scalar_one_or_none()
    if group:
        return group

    group = TagGroup(
        slug=slug,
        title=title,
        is_public=True,
        allow_multiple=allow_multiple,
        sort_order=sort_order,
    )
    session.add(group)
    await session.flush()
    return group


async def _ensure_tag(
    session,
    *,
    group: TagGroup,
    slug: str,
    title: str,
    sort_order: int = 0,
) -> Tag:
    tag = (await session.execute(select(Tag).where(Tag.slug == slug))).scalar_one_or_none()
    if tag:
        changed = False
        if tag.group_id != group.id:
            tag.group_id = group.id
            changed = True
        if not tag.is_filter:
            tag.is_filter = True
            changed = True
        if not tag.is_public:
            tag.is_public = True
            changed = True
        if title and not tag.title:
            tag.title = title
            changed = True
        if changed:
            session.add(tag)
            await session.flush()
        return tag

    tag = Tag(
        slug=slug,
        title=title,
        group_id=group.id,
        is_public=True,
        is_filter=True,
        sort_order=sort_order,
    )
    session.add(tag)
    await session.flush()
    return tag


class ImporterService:
    def __init__(self):
        # Register available parsers
        self.parsers: List[BaseParser] = [
            AircondParser(),
            HaierProffParser(),
            Lg24Parser(),
            HobotParser(),
            TvoyKlimatParser(),
            OnlinerParser(),
        ]

    def get_parser(self, url: str) -> Optional[BaseParser]:
        """Finds a parser that supports the given URL."""
        for parser in self.parsers:
            if parser.supports(url):
                return parser
        return None

    async def import_product(
        self,
        url: str,
        update_existing: bool = False,
        collect_related: bool = False,
    ) -> dict:
        """
        Orchestrates the import process: find parser -> parse -> save to DB.
        Returns a dict: {'product': Product, 'related_urls': List[str]}
        """
        url = url.strip().replace('\r', '').replace('\n', '')
        async with async_session_maker() as session:
            # 0. Check for duplicates (live products only)
            stmt = select(Product).where(Product.source_url == url)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing and not update_existing:
                await session.refresh(existing, attribute_names=["tags"])
                has_category_tag = any(
                    (getattr(tag, "slug", "") or "") in _CATEGORY_TAG_SLUGS
                    for tag in (existing.tags or [])
                )
                if has_category_tag:
                    # Keep fast path for already healthy records.
                    related_urls: List[str] = []
                    if collect_related:
                        parser = self.get_parser(url)
                        if parser:
                            try:
                                parsed = await parser.parse(url)
                                related_urls = list(parsed.get("related_urls") or [])
                            except Exception as exc:
                                logger.warning(
                                    "Failed to collect related URLs for existing product %s (%s): %s",
                                    existing.id,
                                    url,
                                    exc,
                                )
                    return {"product": existing, "related_urls": related_urls}

                # Self-heal path: if product exists but lacks catalog category tags,
                # force update flow to refresh derived tags/specs.
                logger.info(
                    "Reimporting existing product %s because category tags are missing",
                    existing.id,
                )
                update_existing = True

            parser = self.get_parser(url)
            if not parser:
                raise ValueError("No parser found for this URL")

            data = await parser.parse(url)
            await _normalize_import_price_to_byn(session, data=data, source_url=url)
            
            # Determine publishing status
            is_published = True 

            # Resolve Categories/Tags
            tag_names = data.get('categories', [])
            tag_objects = []
            title = data.get("title", "")

            # 1. Get Auto Tags (Slugs) based on metrics/specs/title
            metrics = data.get('metrics', {})
            raw_specs = data.get("specs", {}) or {}
            auto_slugs = get_auto_tags(metrics, specs=raw_specs, title=title)
            # Derive Wi-Fi technical tags from parsed specs so import preserves
            # "builtin" vs "ready" even before any manual manager edits.
            auto_slugs = _augment_auto_slugs_with_wifi_specs(auto_slugs, raw_specs)

            auto_tag_slugs_from_normalizer: List[str] = []
            normalized_specs = normalize_specs(
                raw_specs,
                wifi_tag_slugs=[slug for slug in auto_slugs if slug in {"wifi-builtin", "wifi-ready"}],
                strict_wifi_from_tags=False,
                title=title,
                auto_tag_slugs=auto_tag_slugs_from_normalizer,
            )
            for slug in auto_tag_slugs_from_normalizer:
                if slug not in auto_slugs:
                    auto_slugs.append(slug)

            # Ensure core filter tags exist for brand/category.
            category_slug = detect_category_slug(metrics=metrics, specs=normalized_specs, title=title)
            if category_slug:
                auto_slugs.append(category_slug)
                category_group = await _ensure_tag_group(
                    session,
                    slug="category",
                    title="Категория",
                    allow_multiple=False,
                    sort_order=20,
                )
                await _ensure_tag(
                    session,
                    group=category_group,
                    slug=category_slug,
                    title=CATEGORY_TAG_TITLES.get(category_slug, category_slug),
                )

            brand_slug = extract_brand_slug(specs=normalized_specs, title=title)
            brand_title = extract_brand_name(specs=normalized_specs, title=title)
            if brand_slug and brand_title:
                auto_slugs.append(brand_slug)
                brand_group = await _ensure_tag_group(
                    session,
                    slug="brand",
                    title="Бренд",
                    allow_multiple=False,
                    sort_order=10,
                )
                await _ensure_tag(
                    session,
                    group=brand_group,
                    slug=brand_slug,
                    title=brand_title,
                )

            auto_slugs = list(dict.fromkeys(auto_slugs))

            # 2. Resolve Auto Tags by slug
            for slug in auto_slugs:
                stmt = select(Tag).options(selectinload(Tag.group)).where(Tag.slug == slug)
                result = await session.execute(stmt)
                tag = result.scalar_one_or_none()
                if tag:
                    tag_objects.append(tag)
            
            # 3. Resolve old string categories (Title based)
            for t_name in tag_names:
                t_name = t_name.strip()
                if not t_name: continue
                
                stmt = select(Tag).options(selectinload(Tag.group)).where(Tag.title == t_name)
                result = await session.execute(stmt)
                tag = result.scalar_one_or_none()
                if tag and tag.group and tag.group.slug in {"area", "compressor-type"}:
                    continue
                
                if not tag:
                    slug = slugify.slugify(t_name)
                    tag = Tag(title=t_name, slug=slug, is_public=True)
                    session.add(tag)
                
                if tag not in tag_objects:
                    tag_objects.append(tag)

            # 4. Handle Images (Download to local storage)
            slug = data.get('slug')
            # Fallback if slug missing (shouldn't happen with updated OnlinerParser)
            if not slug:
                slug = slugify.slugify(data['title'])

            # Main Image
            main_image_url = data.get('main_image')
            local_main_image = None
            if main_image_url:
                local_main_image = await ImportMediaService.resolve_or_download(
                    session,
                    source_url=main_image_url,
                )
            
            # --- Gallery images ---
            # Phase 48: Onliner gallery download disabled (manual via Manager).
            # Other donors may return save_gallery=True → persist to ProductImage.
            save_gallery = data.get("save_gallery", False)
            gallery_image_urls: List[str] = []
            if save_gallery:
                gallery_image_urls = data.get("images", [])

            if existing and update_existing:
                # Re-import mode: refresh key business fields, keep photos/slug/title intact.
                existing.description = data.get('description', existing.description)
                existing.price = data.get('price', existing.price)
                existing.area = data.get('area', existing.area)
                existing.is_inverter = metrics.get('is_inverter', existing.is_inverter)
                existing.power_cooling = metrics.get('power_cooling', existing.power_cooling)
                existing.specs = normalized_specs
                existing.source_url = url
                if local_main_image and not existing.main_image:
                    existing.main_image = local_main_image

                # Preserve manual tags, but append newly inferred auto-tags.
                await session.refresh(existing, attribute_names=["tags"])
                merged_tags: dict[str, Tag] = {}
                for tag in (existing.tags or []):
                    key = getattr(tag, "slug", None) or f"id:{getattr(tag, 'id', None)}"
                    merged_tags[key] = tag
                for tag in tag_objects:
                    key = getattr(tag, "slug", None) or f"id:{getattr(tag, 'id', None)}"
                    merged_tags[key] = tag
                existing.tags = list(merged_tags.values())

                session.add(existing)
                product = existing
            else:
                product = Product(
                    title=data['title'],
                    slug=slug,
                    description=data['description'],
                    price=data['price'],
                    area=data['area'],
                    is_inverter=metrics.get('is_inverter', False),
                    power_cooling=metrics.get('power_cooling'),
                    main_image=local_main_image,  # Use local path
                    images=[],  # Explicitly empty legacy JSON
                    tags=tag_objects,
                    specs=normalized_specs,
                    is_published=is_published,
                    source_url=url
                )
                session.add(product)

            await sync_product_brand_series(
                session,
                product=product,
                specs=normalized_specs,
                title=title,
                tags=tag_objects,
            )
            await session.commit()
            await session.refresh(product)

            if "manuals" in data:
                await replace_manuals(
                    session,
                    product_id=product.id,
                    manuals=data.get("manuals") or [],
                )

            # Persist gallery images into ProductImage
            if gallery_image_urls and product.id:
                existing_gallery_urls = set(
                    (
                        await session.execute(
                            select(ProductImage.url).where(ProductImage.product_id == product.id)
                        )
                    ).scalars().all()
                )
                for img_url in gallery_image_urls:
                    try:
                        local_path = await ImportMediaService.resolve_or_download(
                            session,
                            source_url=img_url,
                        )
                        if local_path and local_path not in existing_gallery_urls:
                            pi = ProductImage(
                                product_id=product.id,
                                url=local_path,
                                is_installation_photo=False,
                            )
                            session.add(pi)
                            existing_gallery_urls.add(local_path)
                    except Exception as exc:
                        logger.warning(
                            "Gallery image save failed for %s: %s", img_url, exc
                        )
            if "manuals" in data or gallery_image_urls:
                await session.commit()

            return {"product": product, "related_urls": data.get('related_urls', [])}

    async def import_products_bulk(
        self,
        urls: List[str],
        with_related: bool = False,
        update_existing: bool = False,
    ) -> dict:
        """
        Imports multiple products and returns a summary of success/errors.
        Can recursively import related products.
        """
        results = {"success": [], "errors": []}
        processed_urls = set()
        pending_urls = [u.strip().replace('\r', '').replace('\n', '') for u in urls if u.strip()]

        while pending_urls:
            url = pending_urls.pop(0)
            if url in processed_urls: continue
            
            try:
                res = await self.import_product(
                    url,
                    update_existing=update_existing,
                    collect_related=with_related,
                )
                product = res["product"]
                # Only add to 'success' if it's a NEW import (or just count it)
                # To keep it simple, we count all as success if they are in DB now.
                results["success"].append(f"'{product.title}' (ID: {product.id})")
                
                processed_urls.add(url)
                
                if with_related:
                    for rel_url in res["related_urls"]:
                        if rel_url not in processed_urls and rel_url not in pending_urls:
                            pending_urls.append(rel_url)
            except Exception as e:
                results["errors"].append(f"URL '{url}': {str(e)}")
                processed_urls.add(url)

        return results
