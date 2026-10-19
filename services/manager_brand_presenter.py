"""Manager brand reference payload shared by list and mutation responses."""

from typing import Any

from models import Brand


def serialize_manager_brand(brand: Brand, *, products_count: int = 0) -> dict[str, Any]:
    return {
        "id": brand.id,
        "title": brand.title,
        "slug": brand.slug,
        "logo_url": brand.logo_url,
        "official_url": brand.official_url,
        "short_description": brand.short_description,
        "description": brand.description,
        "is_published": brand.is_published,
        "sort_order": brand.sort_order,
        "created_at": brand.created_at,
        "products_count": int(products_count or 0),
    }
