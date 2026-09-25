"""Create-only public acceptance of an immutable installation preview."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Awaitable, Callable
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Order, OrderProposal, PublicInstallationPreviewClaim, Tenant
from schemas_public_checkout import AcceptedProductLine, OrderPayload, OrderResponse
from services.communications.tenant_website_event_service import TenantWebsiteEventService
from services.installation_estimate_confirmation_service import (
    InstallationEstimateConfirmationService as Confirmation,
    InstallationPriceChanged,
)
from services.installation_price_book_service import InstallationPriceBookService
from services.order_product_link_command import OrderProductCatalogSnapshot
from services.order_service import OrderService
from services.public_catalog_visibility_service import PublicCatalogVisibilityService
from services.public_write_idempotency_service import PublicWriteIdempotencyConflict
from services.service_estimate_money import exact_money, money
from services.storefront_settings_service import StorefrontSettingsService
from services.tenant_scope_service import TenantScope
from core.storefront_request_envelope import private_storefront_response_headers


class PublicInstallationCheckoutService:
    @staticmethod
    def _reject(code: str, status: int = 409) -> HTTPException:
        return HTTPException(status_code=status, detail={"code": code},
                             headers=private_storefront_response_headers())

    @staticmethod
    def _current_lines(
        payload: OrderPayload, snapshots: dict[int, OrderProductCatalogSnapshot],
    ) -> list[AcceptedProductLine]:
        return [AcceptedProductLine(
            product_id=int(item.product_id), quantity=item.quantity,
            unit_price=str(exact_money(snapshots[int(item.product_id)].unit_price)),
            currency=snapshots[int(item.product_id)].currency,
        ) for item in payload.items]

    @classmethod
    def _price_changed(
        cls, *, reason: str, payload: OrderPayload,
        snapshots: dict[int, OrderProductCatalogSnapshot], preview: object | None,
    ) -> HTTPException:
        current_lines = cls._current_lines(payload, snapshots)
        preview_body = preview.model_dump(mode="json") if preview is not None else {}
        preview_total = getattr(preview, "total", None)
        current_total = (
            sum((line.unit_price * line.quantity for line in current_lines), Decimal("0.00"))
            + exact_money(preview_total)
            if getattr(preview, "status", None) == "fixed" and preview_total is not None
            else None
        )
        return HTTPException(status_code=409, detail={
            "code": "price_changed", "reason": reason, "new_consent_required": True,
            "current_product_lines": [line.model_dump(mode="json") for line in current_lines],
            "current_installation_preview": preview_body,
            "current_order_total": str(current_total) if current_total is not None else None,
        }, headers=private_storefront_response_headers())

    @classmethod
    async def create(
        cls, session: AsyncSession, payload: OrderPayload, *, tenant_scope: TenantScope,
        request_key_hash: str, request_fingerprint: str,
        create_order: Callable[[dict[int, OrderProductCatalogSnapshot]], Awaitable[Order]],
    ) -> OrderResponse:
        acceptance = payload.installation_acceptance
        if acceptance is None:
            raise ValueError("Installation acceptance is required")
        if tenant_scope.is_canonical_storefront is not True:
            raise cls._reject("installation_checkout_unavailable", 404)

        # The enclosing checkout receipt has already been claimed. NO KEY UPDATE
        # conflicts with publication and preserves FK KEY SHARE compatibility.
        await session.execute(
            select(Tenant).where(Tenant.id == tenant_scope.tenant_id)
            .with_for_update(key_share=True)
        )
        prior = (await session.execute(select(PublicInstallationPreviewClaim).where(
            PublicInstallationPreviewClaim.tenant_id == tenant_scope.tenant_id,
            PublicInstallationPreviewClaim.storefront_id == tenant_scope.storefront_id,
            PublicInstallationPreviewClaim.checkout_key_hash == request_key_hash,
        ).limit(1))).scalars().first()
        if prior is not None:
            if prior.request_hash != request_fingerprint:
                raise PublicWriteIdempotencyConflict("Idempotency-Key was used with different content")
            if prior.response_body is None:
                raise cls._reject("preview_claim_incomplete", 503)
            return OrderResponse.model_validate(prior.response_body)
        preview_hash = hashlib.sha256(acceptance.preview_ref.encode("ascii")).hexdigest()
        existing_ref = (await session.execute(select(PublicInstallationPreviewClaim).where(
            PublicInstallationPreviewClaim.tenant_id == tenant_scope.tenant_id,
            PublicInstallationPreviewClaim.storefront_id == tenant_scope.storefront_id,
            PublicInstallationPreviewClaim.preview_token_hash == preview_hash,
        ).limit(1))).scalars().first()
        if existing_ref is not None:
            raise cls._reject("preview_already_used")

        product_ids = {int(item.product_id) for item in payload.items}
        snapshots = await PublicCatalogVisibilityService.get_checkout_snapshots(
            session, tenant_scope=tenant_scope, product_ids=product_ids,
        )
        if set(snapshots) != product_ids:
            raise cls._reject("product_not_available", 404)
        if any(snapshot.currency != "BYN" for snapshot in snapshots.values()):
            raise cls._reject("installation_currency_unavailable")
        if not await StorefrontSettingsService.is_service_enabled(
            session, tenant_scope=tenant_scope, service_kind="installation",
        ):
            raise cls._reject("installation_not_available", 404)

        try:
            row, preview_input, accepted = await Confirmation.validated_fixed_preview(
                session, tenant_scope, acceptance.preview_ref,
            )
        except InstallationPriceChanged as exc:
            fresh = await InstallationPriceBookService.preview(
                session, tenant_scope, exc.payload, persist=False,
            )
            raise cls._price_changed(
                reason="installation_price_changed", payload=payload,
                snapshots=snapshots, preview=fresh,
            ) from exc

        if any(item.product_id is None for item in preview_input.installations):
            raise cls._reject("service_only_checkout_unsupported", 422)
        quantities = Counter(item.product_id for item in preview_input.installations)
        cart_quantities = {int(item.product_id): item.quantity for item in payload.items}
        if any(quantities[product_id] > cart_quantities.get(product_id, 0)
               for product_id in quantities):
            raise cls._reject("equipment_not_in_cart", 422)
        if any(snapshots[int(product_id)].unit_price <= 0 for product_id in quantities):
            raise cls._reject("equipment_not_paid", 422)
        if any(component.code == "pump.supply" for component in accepted.components):
            resolutions = {item["key"]: item["resolution"]
                           for item in row.snapshot.get("resolutions", [])}
            if set(quantities) != product_ids or any(
                resolutions.get(item.key, {}).get("profile", {}).get("product_kind")
                != "complete_split_system"
                for item in preview_input.installations
            ):
                raise cls._reject("pump_supply_cart_ambiguous", 422)

        current_lines = cls._current_lines(payload, snapshots)
        expected = {line.product_id: line for line in acceptance.expected_product_lines}
        if any(expected[line.product_id].unit_price != line.unit_price
               or expected[line.product_id].currency != line.currency
               for line in current_lines):
            raise cls._price_changed(
                reason="product_price_changed", payload=payload,
                snapshots=snapshots, preview=accepted,
            )
        current_total = sum(
            (line.unit_price * line.quantity for line in current_lines), Decimal("0.00")
        ) + exact_money(accepted.total)
        if exact_money(acceptance.expected_order_total) != current_total:
            raise cls._price_changed(
                reason="order_total_changed", payload=payload,
                snapshots=snapshots, preview=accepted,
            )

        claim = PublicInstallationPreviewClaim(
            tenant_id=tenant_scope.tenant_id,
            storefront_id=tenant_scope.storefront_id,
            preview_token_hash=row.token_hash,
            checkout_key_hash=request_key_hash,
            request_hash=request_fingerprint,
        )
        session.add(claim)
        await session.flush()

        order = await create_order(snapshots)
        proposal = (await session.execute(select(OrderProposal).where(
            OrderProposal.order_id == order.id,
            OrderProposal.is_selected.is_(True),
            OrderProposal.is_archived.is_(False),
        ))).scalars().one()
        estimate_key = hashlib.sha256(
            f"public_checkout:{request_key_hash}".encode("ascii")
        ).hexdigest()
        _, revision = await Confirmation.persist_revision(
            session, tenant_scope, row=row, result=accepted,
            order_id=int(order.id), proposal_id=int(proposal.id),
            key_hash=estimate_key, request_hash=request_fingerprint,
            actor="public_checkout", verified_service_only_keys=[],
        )
        session.add_all(Confirmation.new_revision_lines(
            order_id=int(order.id), proposal_id=int(proposal.id),
            saved=revision, mode="collapsed",
        ))
        await session.flush()
        await OrderService._refresh_order_financials(session, order)
        if money(order.total_amount) != current_total:
            raise cls._reject("installation_total_mismatch")
        session.add(order)
        await TenantWebsiteEventService.enqueue_checkout(
            session, order=order, request=payload,
            tenant_scope=tenant_scope, request_key_hash=request_key_hash,
        )
        response = OrderResponse(
            id=int(order.id), status=order.status,
            total_amount=order.total_amount, created_at=order.created_at,
        )
        claim.order_id = int(order.id)
        claim.response_body = response.model_dump(mode="json")
        session.add(claim)
        return response
