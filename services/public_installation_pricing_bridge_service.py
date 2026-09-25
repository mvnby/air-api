"""Read-only public transition from legacy installation prices to a published book."""

from sqlalchemy.ext.asyncio import AsyncSession

from models.tenancy import TenantScope
from schemas_installation_price_book import (
    InstallationPricingCapabilities,
    InstallationPricingConfigResponse,
)
from services.content_api_service import ContentApiService
from services.installation_price_book_service import InstallationPriceBookService
from services.storefront_settings_service import StorefrontSettingsService


class PublicInstallationPricingBridgeService:
    LEGACY_INSTALLATION_CATEGORIES = frozenset({"installation", "installation_option"})

    @classmethod
    async def config(
        cls, session: AsyncSession, scope: TenantScope,
    ) -> InstallationPricingConfigResponse:
        book = await InstallationPriceBookService.latest(session, scope)
        enabled = await StorefrontSettingsService.is_service_enabled(
            session, tenant_scope=scope, service_kind="installation",
        )
        has_book = book is not None
        return InstallationPricingConfigResponse(
            source="price_book" if has_book else "legacy",
            price_book_revision=book.revision if book else None,
            scope_ref=InstallationPriceBookService._scope_ref(scope),
            service_enabled=enabled,
            capabilities=InstallationPricingCapabilities(
                legacy_rate_checkout=enabled and not has_book,
                standard_product_acceptance=(
                    enabled and has_book and scope.is_canonical_storefront is True
                ),
                manual_service_only_preview=enabled and has_book,
                multisplit_preview_only=enabled and has_book,
                prelaid_preview_only=enabled and has_book,
            ),
        )

    @classmethod
    async def visible_content_services(
        cls, session: AsyncSession, scope: TenantScope,
    ) -> list[dict]:
        services = await ContentApiService.get_active_services(
            session, tenant_scope=scope,
        )
        if await InstallationPriceBookService.latest(session, scope):
            return [
                service for service in services
                if service["category"] not in cls.LEGACY_INSTALLATION_CATEGORIES
            ]
        return services

    @classmethod
    async def legacy_option_category_available(
        cls, session: AsyncSession, scope: TenantScope, category: str,
    ) -> bool:
        return (
            category not in cls.LEGACY_INSTALLATION_CATEGORIES
            or await InstallationPriceBookService.latest(session, scope) is None
        )
