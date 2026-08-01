"""Service-layer helpers for public content/services/config endpoints."""

from typing import Any, Dict, List

from bs4 import BeautifulSoup

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Brand, Feature, FeatureBrandLink, GlobalConfig, Product, Service
from models.tenancy import TenantScope
from crud.public_catalog import PublicCatalogDAO
from services.feature_scope_policy import FeatureScopePolicy
from services.public_catalog_service import PublicCatalogService


class ContentApiService:
    PUBLIC_CONFIG_KEYS = frozenset(
        {
            "phone",
            "phone_clean",
            "email",
            "address",
            "work_hours",
            "install_discount",
        }
    )
    _ALLOWED_HTML_TAGS = {
        "p", "br", "ul", "ol", "li", "strong", "b", "em", "i", "a", "h2", "h3", "h4", "blockquote",
    }
    _ALLOWED_HTML_ATTRS = {
        "a": {"href", "title", "target", "rel"},
    }
    _DANGEROUS_URI_SCHEMES = ("javascript:", "data:", "vbscript:")

    @staticmethod
    def _sanitize_service_description(value: str | None) -> str | None:
        if value is None:
            return None

        raw = str(value).strip()
        if not raw:
            return None

        soup = BeautifulSoup(raw, "html.parser")

        for dangerous_tag in soup.find_all(["script", "style", "iframe", "object", "embed"]):
            dangerous_tag.decompose()

        for tag in soup.find_all(True):
            if tag.name not in ContentApiService._ALLOWED_HTML_TAGS:
                tag.unwrap()
                continue

            allowed_attrs = ContentApiService._ALLOWED_HTML_ATTRS.get(tag.name, set())
            for attr_name in list(tag.attrs.keys()):
                attr_name_l = attr_name.lower()
                if attr_name_l.startswith("on") or attr_name_l not in allowed_attrs:
                    del tag.attrs[attr_name]

            if tag.name == "a":
                href = str(tag.get("href") or "").strip()
                if not href or href.lower().startswith(ContentApiService._DANGEROUS_URI_SCHEMES):
                    tag.attrs.pop("href", None)
                target = str(tag.get("target") or "").strip().lower()
                if target == "_blank":
                    rel_parts = tag.get("rel") or []
                    if isinstance(rel_parts, str):
                        rel_parts = rel_parts.split()
                    rel_set = {str(part).strip().lower() for part in rel_parts if str(part).strip()}
                    rel_set.update({"noopener", "noreferrer"})
                    tag.attrs["rel"] = sorted(rel_set)
                else:
                    tag.attrs.pop("rel", None)

        sanitized = str(soup).strip()
        return sanitized or None

    @staticmethod
    def _serialize_service(service: Service) -> Dict[str, Any]:
        return {
            "id": service.id,
            "title": service.title,
            "slug": service.slug,
            "category": service.category,
            "is_active": service.is_active,
            "image": service.image,
            "description": ContentApiService._sanitize_service_description(service.description),
            "base_price": service.base_price,
        }

    @staticmethod
    def _serialize_brand_feature(feature: Feature) -> Dict[str, Any]:
        return {
            "id": feature.id,
            "title": feature.name,
            "slug": feature.slug,
            "text": feature.full_description,
            "image_url": feature.image_url,
            "icon": feature.icon,
            "footnote": feature.footnote,
            "source_url": feature.source_url,
            "aliases": feature.aliases or [],
            "is_published": feature.is_active,
            "sort_order": int(feature.sort_order or 0),
        }

    @staticmethod
    def _serialize_brand_features(brand: Brand) -> List[Dict[str, Any]]:
        features = list(getattr(brand, "__dict__", {}).get("_resolved_brand_features") or [])
        published = [feature for feature in features if getattr(feature, "is_active", False)]
        published.sort(
            key=lambda feature: (
                int(getattr(feature, "sort_order", 0) or 0),
                str(getattr(feature, "name", "") or "").casefold(),
                int(getattr(feature, "id", 0) or 0),
            )
        )
        return [ContentApiService._serialize_brand_feature(feature) for feature in published]

    @staticmethod
    def _serialize_brand(
        brand: Brand,
        *,
        products_count: int,
        include_features: bool = False,
    ) -> Dict[str, Any]:
        payload = {
            "id": brand.id,
            "title": brand.title,
            "slug": brand.slug,
            "logo_url": brand.logo_url,
            "description": brand.description,
            "products_count": int(products_count or 0),
            "sort_order": brand.sort_order,
        }
        if include_features:
            payload["features"] = ContentApiService._serialize_brand_features(brand)
        return payload

    @staticmethod
    async def get_active_services(session: AsyncSession) -> List[Dict[str, Any]]:
        stmt = select(Service).where(Service.is_active == True).order_by(Service.id)
        result = await session.execute(stmt)
        return [ContentApiService._serialize_service(service) for service in result.scalars().all()]

    @staticmethod
    async def get_service_options(
        session: AsyncSession,
        category: str = "installation_option",
    ) -> List[Dict[str, Any]]:
        stmt = (
            select(Service)
            .where(Service.is_active == True)
            .where(Service.category == category)
            .order_by(Service.base_price)
        )
        result = await session.execute(stmt)
        return [ContentApiService._serialize_service(service) for service in result.scalars().all()]

    @staticmethod
    async def get_public_brands(
        session: AsyncSession,
        tenant_scope: TenantScope | None = None,
    ) -> List[Dict[str, Any]]:
        if tenant_scope is not None and not await PublicCatalogService.is_canonical_scope(
            session,
            tenant_scope,
        ):
            rows = await PublicCatalogDAO.list_brand_counts(
                session,
                tenant_scope=tenant_scope,
            )
        else:
            stmt = (
                select(Brand, func.count(Product.id).label("products_count"))
                .join(Product, Product.brand_id == Brand.id)
                .where(Brand.is_published == True)
                .where(Product.is_published == True)
                .group_by(Brand.id)
                .having(func.count(Product.id) > 0)
                .order_by(Brand.sort_order.asc(), Brand.title.asc())
            )
            rows = list((await session.execute(stmt)).all())
        return [
            ContentApiService._serialize_brand(brand, products_count=products_count)
            for brand, products_count in rows
        ]

    @staticmethod
    async def get_public_brand_by_slug(
        session: AsyncSession,
        slug: str,
        tenant_scope: TenantScope | None = None,
    ) -> Dict[str, Any] | None:
        if tenant_scope is not None and not await PublicCatalogService.is_canonical_scope(
            session,
            tenant_scope,
        ):
            rows = await PublicCatalogDAO.list_brand_counts(
                session,
                tenant_scope=tenant_scope,
                brand_slug=slug,
            )
            row = rows[0] if rows else None
        else:
            stmt = (
                select(Brand, func.count(Product.id).label("products_count"))
                .join(Product, Product.brand_id == Brand.id)
                .where(Brand.is_published == True)
                .where(Brand.slug == slug)
                .where(Product.is_published == True)
                .group_by(Brand.id)
                .having(func.count(Product.id) > 0)
            )
            row = (await session.execute(stmt)).one_or_none()
        if row is None:
            return None
        brand, products_count = row
        features = list(
            (
                await session.execute(
                    select(Feature)
                    .join(FeatureBrandLink, FeatureBrandLink.feature_id == Feature.id)
                    .where(
                        FeatureBrandLink.brand_id == brand.id,
                        FeatureBrandLink.is_enabled.is_(True),
                        Feature.is_active.is_(True),
                    )
                    .order_by(FeatureBrandLink.sort_order, Feature.sort_order, Feature.name)
                )
            ).scalars().all()
        )
        features = [
            feature
            for feature in features
            if FeatureScopePolicy.allows_target(
                feature,
                target_type="brand",
                brand_id=int(brand.id),
            )
        ]
        brand.__dict__["_resolved_brand_features"] = features
        return ContentApiService._serialize_brand(brand, products_count=products_count, include_features=True)

    @staticmethod
    async def get_global_config_map(session: AsyncSession) -> Dict[str, str]:
        stmt = select(GlobalConfig).where(GlobalConfig.key.in_(ContentApiService.PUBLIC_CONFIG_KEYS))
        result = await session.execute(stmt)
        configs = result.scalars().all()
        return {
            config.key: config.value
            for config in configs
            if config.key in ContentApiService.PUBLIC_CONFIG_KEYS
        }
