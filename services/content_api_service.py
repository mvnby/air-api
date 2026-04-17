"""Service-layer helpers for public content/services/config endpoints."""

from typing import Any, Dict, List

from bs4 import BeautifulSoup

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import GlobalConfig, Service


class ContentApiService:
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
    async def get_global_config_map(session: AsyncSession) -> Dict[str, str]:
        stmt = select(GlobalConfig)
        result = await session.execute(stmt)
        configs = result.scalars().all()
        return {config.key: config.value for config in configs}
