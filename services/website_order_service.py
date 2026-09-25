"""Service-layer orchestration for website checkout orders."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from models import LeadSource, Order, OrderStatus
from schemas import OrderPayload, OrderResponse
from services.communications.tenant_website_event_service import (
    TenantWebsiteEventService,
)
from services.installation_pricing_service import (
    InstallationPricingError,
    InstallationPricingService,
)
from services.order_product_link_command import (
    OrderProductCatalogSnapshot,
    OrderProductLinkCommand,
)
from services.order_service import OrderService
from services.public_catalog_visibility_service import PublicCatalogVisibilityService
from services.public_write_fingerprint_service import PublicWriteFingerprintService
from services.public_write_idempotency_service import (
    PublicWriteCommandResponse,
    PublicWriteIdempotencyService,
)
from services.tenant_scope_service import TenantScope
from services.storefront_settings_service import StorefrontSettingsService
from services.public_installation_checkout_service import PublicInstallationCheckoutService

logger = logging.getLogger(__name__)


class WebsiteOrderService:
    @staticmethod
    async def create_order(
        session: AsyncSession,
        payload: OrderPayload,
        *,
        tenant_scope: TenantScope,
        idempotency_key: str,
    ) -> OrderResponse:
        request_key_hash = PublicWriteIdempotencyService.key_hash(
            idempotency_key
        )
        request_fingerprint = PublicWriteFingerprintService.for_payload(
            payload if payload.installation_acceptance is not None else
            payload.model_dump(mode="json", exclude={"installation_acceptance"})
        )

        async def create() -> PublicWriteCommandResponse[OrderResponse]:
            if payload.installation_acceptance is not None:
                async def create_accepted_order(snapshots):
                    return await WebsiteOrderService._create_order_mutation(
                        session, payload, tenant_scope=tenant_scope,
                        request_key_hash=request_key_hash,
                        catalog_snapshots=snapshots, accepted_installation=True,
                    )

                response = await PublicInstallationCheckoutService.create(
                    session, payload, tenant_scope=tenant_scope,
                    request_key_hash=request_key_hash,
                    request_fingerprint=request_fingerprint,
                    create_order=create_accepted_order,
                )
                return PublicWriteCommandResponse(
                    value=response, resource_type="order", resource_id=response.id,
                )
            created_order = await WebsiteOrderService._create_order_mutation(
                session,
                payload,
                tenant_scope=tenant_scope,
                request_key_hash=request_key_hash,
            )
            response = OrderResponse(
                id=created_order.id,
                status=created_order.status,
                total_amount=created_order.total_amount,
                created_at=created_order.created_at,
            )
            return PublicWriteCommandResponse(
                value=response,
                resource_type="order",
                resource_id=int(created_order.id or 0),
            )

        outcome = await PublicWriteIdempotencyService.execute(
            session,
            tenant_scope=tenant_scope,
            command_name="public_order_checkout_v1",
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            response_model=OrderResponse,
            operation=create,
        )
        return outcome.value

    @staticmethod
    async def _create_order_mutation(
        session: AsyncSession,
        payload: OrderPayload,
        *,
        tenant_scope: TenantScope,
        request_key_hash: str,
        catalog_snapshots: dict[int, OrderProductCatalogSnapshot] | None = None,
        accepted_installation: bool = False,
    ) -> Order:
        logger.info(
            "PUBLIC_CHECKOUT_RECEIVED item_count=%s installation_item_count=%s",
            len(payload.items),
            len([item for item in payload.items if item.with_installation]),
        )
        product_ids = {
            int(item.product_id)
            for item in payload.items
            if item.product_id is not None
        }
        storefront_snapshots: dict[int, OrderProductCatalogSnapshot] = catalog_snapshots or {}
        if product_ids and catalog_snapshots is None:
            storefront_snapshots = (
                await PublicCatalogVisibilityService.get_checkout_snapshots(
                    session,
                    tenant_scope=tenant_scope,
                    product_ids=product_ids,
                )
            )
        missing_product_ids = sorted(product_ids - storefront_snapshots.keys())
        if missing_product_ids:
            raise InstallationPricingError(
                f"Товар #{missing_product_ids[0]} недоступен для этой витрины",
                code="product_not_available",
            )
        if any(item.with_installation for item in payload.items) and not (
            await StorefrontSettingsService.is_service_enabled(
                session,
                tenant_scope=tenant_scope,
                service_kind="installation",
            )
        ):
            raise InstallationPricingError(
                "Монтаж недоступен для этой витрины",
                code="installation_not_available",
            )
        items = (
            [item.model_dump() for item in payload.items]
            if accepted_installation else
            await InstallationPricingService.price_public_items(
                session, payload.items, catalog_snapshots=storefront_snapshots,
                tenant_scope=tenant_scope,
            )
        )
        pricing_snapshots = [
            {
                "item_index": index,
                "product_id": item["product_id"],
                "quantity": item["quantity"],
                "installation_meta": item["installation_meta"],
            }
            for index, item in enumerate(items)
            if item["with_installation"]
        ]
        catalog_pricing_snapshots = [
            storefront_snapshots[int(item["product_id"])].as_technical_meta()
            for item in items
            if item.get("product_id") is not None
        ]
        technical_meta = {}
        if catalog_pricing_snapshots:
            technical_meta["public_catalog_pricing"] = {
                "snapshot_version": 1,
                "items": catalog_pricing_snapshots,
            }
        if pricing_snapshots:
            technical_meta["public_installation_pricing"] = {
                "pricing_version": InstallationPricingService.PRICING_VERSION,
                "items": pricing_snapshots,
            }

        order = await OrderService.create_from_website(
            session=session,
            customer_name=payload.customer.name,
            customer_phone=payload.customer.phone,
            customer_email=payload.customer.email,
            customer_address=payload.customer.address,
            items=items,
            lead_source=LeadSource.SITE,
            initial_status=OrderStatus.NEGOTIATION,
            comment=payload.comment,
            customer_type=payload.customer.type,
            customer_inn=payload.customer.inn,
            customer_full_legal_name=payload.customer.full_legal_name,
            customer_legal_address=payload.customer.legal_address,
            customer_iban=payload.customer.iban,
            customer_bic=payload.customer.bic,
            customer_bank_name=payload.customer.bank_name,
            order_technical_meta=technical_meta or None,
            product_link_command=OrderProductLinkCommand.storefront_snapshot(
                storefront_snapshots
            ),
            tenant_scope=tenant_scope,
            commit=False,
        )
        if not accepted_installation:
            await TenantWebsiteEventService.enqueue_checkout(
                session, order=order, request=payload,
                tenant_scope=tenant_scope, request_key_hash=request_key_hash,
            )
        return order
