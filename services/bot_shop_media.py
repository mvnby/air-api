"""Prepare product-gallery images and approved mobile variants for staff Telegram."""

from urllib.parse import unquote, urlsplit

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only, selectinload
from sqlmodel import select

from api_contracts.bot_shop import BotShopImage
from core.config import settings
from core.input_validation import validate_public_manual_url
from models import Product, ProductImage, TenantOffer
from models.tenancy import TenantScope
from services.catalog_decision_projection import CatalogDecisionQueryService
from services.catalog_media_policy import CANONICAL_MEDIA_ORIGIN
from services.product_image_processing_contract import ProductImageVariantType
from services.product_response_mapper import (
    _approved_ready_variant_url,
    _is_same_image_url,
    _public_image_url,
    _public_legacy_image_urls,
)
from services.product_serialization import parse_legacy_images


def _photo_url(value: str | None) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    value = value.strip()
    if value.startswith("media/"):
        value = "/" + value
    try:
        url = urlsplit(validate_public_manual_url(value))
    except ValueError:
        return None
    site = urlsplit(settings.PUBLIC_SITE_URL)
    cdn = urlsplit(settings.PRODUCT_MEDIA_S3_PUBLIC_BASE_URL or CANONICAL_MEDIA_ORIGIN)
    if url.query or "#" in value or any(
        unquote(part) in {".", ".."} or "/" in unquote(part) or "\\" in unquote(part)
        for part in url.path.split("/")
    ):
        return None
    if not url.path.lower().endswith((".webp", ".jpg", ".jpeg", ".png", ".avif", ".gif")):
        return None
    local_path = url.path.startswith("/media/products/") or (
        url.path.startswith("/media/") and url.path.count("/") == 2
    )
    if not url.scheme:
        return f"https://{site.netloc}{url.path}" if local_path and site.scheme == "https" else None
    if url.scheme != "https":
        return None
    if url.netloc == site.netloc and local_path:
        return url.geturl()
    if url.netloc in {cdn.netloc, urlsplit(CANONICAL_MEDIA_ORIGIN).netloc} and (
        url.path.startswith("/products/") or url.path.startswith("/media/products/")
    ):
        return url.geturl()
    return None


def gallery(product: Product) -> list[BotShopImage]:
    ordered = sorted(product.gallery_images or [], key=lambda image: image.id)
    primary = next((image for image in ordered if _is_same_image_url(image.url, product.main_image)), None)
    seen: set[str] = set()
    result: list[BotShopImage] = []

    def add(original: str | None, *, image: ProductImage | None = None):
        full = thumbnail = None
        if image:
            full = _photo_url(_approved_ready_variant_url(image, ProductImageVariantType.FULL))
            thumbnail = _photo_url(_approved_ready_variant_url(image, ProductImageVariantType.CARD))
        original_url = _photo_url(original) or (_photo_url(image.url) if image else None)
        url = full or original_url or thumbnail
        if url is None or url in seen or (original_url is not None and original_url in seen):
            return
        seen.add(url)
        if original_url:
            seen.add(original_url)
        result.append(BotShopImage(url=url, thumbnail_url=thumbnail or original_url or url, alt=product.title))

    if primary is None:
        add(product.main_image)
    else:
        add(_public_image_url(primary), image=primary)
    for image in ordered:
        if image is not primary:
            add(_public_image_url(image), image=image)
    legacy = [entry for entry in parse_legacy_images(product.images) if isinstance(entry, str)]
    for url in _public_legacy_image_urls(product, legacy):
        add(url)
    return result


async def scoped_products(
    session: AsyncSession, scope: TenantScope, ids: list[int], *, detail: bool = False,
) -> dict[int, Product]:
    if not ids:
        return {}
    columns = [Product.id, Product.title, Product.main_image, Product.images]
    if detail:
        columns.extend([Product.description, Product.specs, Product.brand_id, Product.series_id,
                        Product.is_inverter, Product.power_cooling])
    query = (
        select(Product).where(Product.id.in_(ids), CatalogDecisionQueryService._complete_split_condition(session))
        .options(load_only(*columns), selectinload(Product.gallery_images).selectinload(ProductImage.variants))
    )
    if not scope.is_system:
        query = query.join(TenantOffer, TenantOffer.product_id == Product.id).where(
            *CatalogDecisionQueryService._visible_offer_conditions(scope),
        )
    return {product.id: product for product in (await session.execute(query)).scalars()}
