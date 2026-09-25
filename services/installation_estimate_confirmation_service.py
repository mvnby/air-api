"""Confirm immutable installation previews and attach exact revisions to proposals."""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    InstallationEstimate, InstallationEstimateRevision, InstallationPreviewSnapshot,
    Order, OrderProductLink, OrderProposal, OrderServiceLink, Tenant,
)
from models.tenancy import TenantScope
from schemas_installation_confirmation import (
    ManagerInstallationAttachPayload, ManagerInstallationAttachResponse,
    ManagerInstallationAttachedLine, ManagerInstallationConfirmPayload,
    ManagerInstallationConfirmResponse, ManagerInstallationEstimateRevisionResponse,
)
from schemas_installation_price_book import InstallationPreviewPayload, InstallationPreviewResponse
from services.installation_price_book_service import InstallationPriceBookService
from services.installation_preview_receipt_service import InstallationPreviewReceiptService
from services.order_proposal_command_service import OrderProposalCommandService
from services.order_proposal_lifecycle import PROPOSAL_STATUS_APPROVED, PROPOSAL_STATUS_SENT, normalize_proposal_status
from services.order_service import OrderService
from services.public_write_idempotency_service import (
    PublicWriteCommandOutcome, PublicWriteCommandResponse, PublicWriteIdempotencyConflict,
    PublicWriteIdempotencyService,
)
from services.service_estimate_money import exact_money, writable_service_money


class InstallationPriceChanged(Exception):
    def __init__(self, payload: InstallationPreviewPayload, current_revision: int | None):
        self.payload = payload
        self.current_revision = current_revision


class InstallationEstimateConfirmationService:
    ATTACH_RESPONSE_MAX_BYTES = 256 * 1024

    @staticmethod
    def _bad(code: str, status_code: int = 409) -> HTTPException:
        return HTTPException(status_code=status_code, detail={"code": code})

    @staticmethod
    def _fingerprint(value: object) -> str:
        data = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
        encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(encoded.encode()).hexdigest()

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    @classmethod
    async def _order(cls, session: AsyncSession, scope: TenantScope, order_id: int) -> Order:
        try:
            return await OrderProposalCommandService._load_order_for_write(
                session, order_id, tenant_scope=scope,
            )
        except ValueError as exc:
            raise cls._bad("estimate_target_not_found", 404) from exc

    @classmethod
    def _proposal(cls, order: Order, proposal_id: int) -> OrderProposal:
        proposal = next((item for item in order.proposals
                         if item.id == proposal_id and not item.is_archived), None)
        if proposal is None:
            raise cls._bad("estimate_target_not_found", 404)
        return proposal

    @classmethod
    def _editable(cls, proposal: OrderProposal) -> None:
        if normalize_proposal_status(proposal.status) in {PROPOSAL_STATUS_SENT, PROPOSAL_STATUS_APPROVED}:
            raise cls._bad("proposal_not_editable")

    @classmethod
    async def _preview_row(
        cls, session: AsyncSession, scope: TenantScope, preview_ref: str,
    ) -> InstallationPreviewSnapshot:
        token_hash = hashlib.sha256(preview_ref.encode()).hexdigest()
        statement = select(InstallationPreviewSnapshot).where(
            InstallationPreviewSnapshot.token_hash == token_hash,
            InstallationPreviewSnapshot.tenant_id == scope.tenant_id,
            InstallationPreviewSnapshot.storefront_id == scope.storefront_id,
        ).limit(1)
        if session.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update(read=True)
        row = (await session.execute(statement)).scalars().first()
        if row is None or not hmac.compare_digest(InstallationPreviewReceiptService._token(row), preview_ref):
            raise cls._bad("preview_not_found", 404)
        if cls._utc(row.expires_at) <= datetime.now(timezone.utc):
            raise cls._bad("preview_expired")
        return row

    @classmethod
    def _verify_equipment(
        cls, order: Order, proposal_id: int, input_payload: InstallationPreviewPayload,
        verified_service_only_keys: list[str],
    ) -> None:
        manual = {item.key for item in input_payload.installations if item.typed_profile is not None}
        if len(verified_service_only_keys) != len(set(verified_service_only_keys)) or set(verified_service_only_keys) != manual:
            raise cls._bad("service_only_verification_required", 422)
        if any(not item.typed_profile.confirmed for item in input_payload.installations
               if item.typed_profile is not None):
            raise cls._bad("service_only_profile_unconfirmed", 422)
        needed = Counter(item.product_id for item in input_payload.installations if item.product_id is not None)
        available: Counter[int] = Counter()
        for link in order.product_links:
            if link.proposal_id == proposal_id and link.product_id is not None and link.quantity > 0 \
               and Decimal(str(link.price)) > 0 and not link.is_installation_included:
                available[int(link.product_id)] += int(link.quantity)
        if any(available[product_id] < count for product_id, count in needed.items()):
            raise cls._bad("equipment_not_in_proposal", 422)

    @classmethod
    async def validate_attached_claims(
        cls, session: AsyncSession, order_id: int, proposal_id: int,
        *, incoming: InstallationPreviewPayload | None = None,
    ) -> None:
        """Keep installation identities and sold equipment capacity unique per proposal."""
        revision_ids = list((await session.execute(select(
            OrderServiceLink.installation_estimate_revision_id,
        ).where(
            OrderServiceLink.order_id == order_id,
            OrderServiceLink.proposal_id == proposal_id,
            OrderServiceLink.installation_estimate_revision_id.is_not(None),
        ).distinct())).scalars())
        snapshots = list((await session.execute(select(InstallationEstimateRevision).where(
            InstallationEstimateRevision.id.in_(revision_ids),
        ))).scalars()) if revision_ids else []
        payloads = [InstallationPreviewPayload.model_validate(saved.snapshot["input"])
                    for saved in snapshots]
        if incoming is not None:
            payloads.append(incoming)
        seen_keys: set[str] = set()
        needed: Counter[int] = Counter()
        for payload in payloads:
            for item in payload.installations:
                if item.key in seen_keys:
                    raise ValueError("Installation identity is already attached to this proposal")
                seen_keys.add(item.key)
                if item.product_id is not None:
                    needed[int(item.product_id)] += 1
        if not needed:
            return
        available: Counter[int] = Counter()
        links = (await session.execute(select(OrderProductLink).where(
            OrderProductLink.order_id == order_id,
            OrderProductLink.proposal_id == proposal_id,
        ))).scalars()
        for link in links:
            if link.product_id is not None and link.quantity > 0 and Decimal(str(link.price)) > 0 \
               and not link.is_installation_included:
                available[int(link.product_id)] += int(link.quantity)
        if any(available[product_id] < count for product_id, count in needed.items()):
            raise ValueError("Attached installation equipment exceeds the target proposal quantity")

    @classmethod
    def _confirm_response(
        cls, estimate: InstallationEstimate, revision: InstallationEstimateRevision,
    ) -> ManagerInstallationConfirmResponse:
        result = InstallationPreviewResponse.model_validate(revision.snapshot["result"])
        return ManagerInstallationConfirmResponse(
            estimate_id=int(estimate.id), revision=revision.revision,
            order_id=estimate.order_id, proposal_id=estimate.proposal_id,
            price_book_id=revision.price_book_id, price_book_revision=revision.price_book_revision,
            total=exact_money(revision.total), customer_text=result.customer_text or "",
            created_at=revision.created_at,
        )

    @classmethod
    async def confirm(
        cls, session: AsyncSession, scope: TenantScope, payload: ManagerInstallationConfirmPayload,
        *, idempotency_key: str, actor: str,
    ) -> PublicWriteCommandOutcome[ManagerInstallationConfirmResponse]:
        fingerprint = cls._fingerprint(payload)
        key_hash = PublicWriteIdempotencyService.key_hash(idempotency_key)

        async def operation() -> PublicWriteCommandResponse[ManagerInstallationConfirmResponse]:
            # Publication takes this lock before deriving and committing a new
            # price-book revision. Keep it through this command's commit so an
            # accepted preview cannot cross a concurrent publication boundary.
            await session.execute(
                select(Tenant).where(Tenant.id == scope.tenant_id).with_for_update(key_share=True)
            )
            previous = (await session.execute(select(InstallationEstimate).where(
                InstallationEstimate.tenant_id == scope.tenant_id,
                InstallationEstimate.storefront_id == scope.storefront_id,
                InstallationEstimate.confirmation_key_hash == key_hash,
            ).limit(1))).scalars().first()
            if previous is not None:
                if previous.confirmation_request_hash != fingerprint:
                    raise PublicWriteIdempotencyConflict("Confirmation key was used with different input")
                previous_revision = (await session.execute(select(InstallationEstimateRevision).where(
                    InstallationEstimateRevision.estimate_id == previous.id,
                    InstallationEstimateRevision.revision == 1,
                ))).scalars().one()
                return PublicWriteCommandResponse(
                    value=cls._confirm_response(previous, previous_revision), status_code=201,
                    resource_type="installation_estimate", resource_id=previous.id,
                )

            order = await cls._order(session, scope, payload.order_id)
            preview_token_hash = hashlib.sha256(payload.preview_ref.encode()).hexdigest()
            already_accepted = (await session.execute(select(InstallationEstimate).where(
                InstallationEstimate.tenant_id == scope.tenant_id,
                InstallationEstimate.storefront_id == scope.storefront_id,
                InstallationEstimate.preview_token_hash == preview_token_hash,
                InstallationEstimate.order_id == payload.order_id,
                InstallationEstimate.proposal_id == payload.proposal_id,
            ).limit(1))).scalars().first()
            if already_accepted is not None:
                previous_revision = (await session.execute(select(InstallationEstimateRevision).where(
                    InstallationEstimateRevision.estimate_id == already_accepted.id,
                    InstallationEstimateRevision.revision == 1,
                ))).scalars().one()
                verified = previous_revision.snapshot.get("confirmation", {}).get("verified_service_only_keys", [])
                if sorted(payload.verified_service_only_keys) != verified:
                    raise cls._bad("preview_already_confirmed")
                return PublicWriteCommandResponse(
                    value=cls._confirm_response(already_accepted, previous_revision), status_code=201,
                    resource_type="installation_estimate", resource_id=already_accepted.id,
                )

            proposal = cls._proposal(order, payload.proposal_id)
            cls._editable(proposal)
            row = await cls._preview_row(session, scope, payload.preview_ref)
            result = InstallationPreviewResponse.model_validate(row.snapshot["result"])
            if result.status != "fixed" or result.total is None:
                raise cls._bad("preview_not_fixed")
            if result.price_book_id != row.price_book_id or result.price_book_revision is None:
                raise cls._bad("invalid_preview_snapshot")
            input_payload = InstallationPreviewPayload.model_validate(row.snapshot["input"])
            cls._verify_equipment(order, payload.proposal_id, input_payload, payload.verified_service_only_keys)
            try:
                await cls.validate_attached_claims(
                    session, payload.order_id, payload.proposal_id, incoming=input_payload,
                )
            except ValueError as exc:
                raise cls._bad("installation_already_attached") from exc
            latest = await InstallationPriceBookService.latest(session, scope)
            if latest is None or latest.id != row.price_book_id:
                raise InstallationPriceChanged(input_payload, latest.revision if latest else None)
            fresh = await InstallationPriceBookService.preview(
                session, scope, input_payload, persist=False,
            )
            if fresh.status != "fixed" or fresh.total != result.total or fresh.components != result.components \
               or fresh.installations != result.installations or fresh.site_work != result.site_work:
                raise InstallationPriceChanged(input_payload, latest.revision)

            estimate = InstallationEstimate(
                tenant_id=scope.tenant_id, storefront_id=scope.storefront_id,
                order_id=payload.order_id, proposal_id=payload.proposal_id,
                confirmation_key_hash=key_hash, confirmation_request_hash=fingerprint,
                preview_token_hash=preview_token_hash,
                created_by=actor,
            )
            session.add(estimate)
            await session.flush()
            snapshot = copy.deepcopy(row.snapshot)
            snapshot["confirmation"] = {
                "order_id": payload.order_id, "proposal_id": payload.proposal_id,
                "verified_service_only_keys": sorted(payload.verified_service_only_keys),
                "actor": actor, "confirmed_at": datetime.now(timezone.utc).isoformat(),
            }
            revision = InstallationEstimateRevision(
                estimate_id=int(estimate.id), revision=1, price_book_id=row.price_book_id,
                price_book_revision=result.price_book_revision,
                total=exact_money(result.total), snapshot=snapshot,
            )
            cls._projection(revision, "collapsed")
            cls._projection(revision, "detailed")
            session.add(revision)
            await session.flush()
            return PublicWriteCommandResponse(
                value=cls._confirm_response(estimate, revision), status_code=201,
                resource_type="installation_estimate", resource_id=estimate.id,
            )

        return await PublicWriteIdempotencyService.execute(
            session, tenant_scope=scope, command_name="manager_installation_confirm_v1",
            idempotency_key=idempotency_key, request_fingerprint=fingerprint,
            response_model=ManagerInstallationConfirmResponse, operation=operation,
        )

    @classmethod
    async def _revision(
        cls, session: AsyncSession, scope: TenantScope, estimate_id: int, revision: int,
    ) -> tuple[InstallationEstimate, InstallationEstimateRevision]:
        result = (await session.execute(select(InstallationEstimate, InstallationEstimateRevision).join(
            InstallationEstimateRevision,
            InstallationEstimateRevision.estimate_id == InstallationEstimate.id,
        ).where(
            InstallationEstimate.id == estimate_id,
            InstallationEstimate.tenant_id == scope.tenant_id,
            InstallationEstimate.storefront_id == scope.storefront_id,
            InstallationEstimateRevision.revision == revision,
        ).limit(1))).first()
        if result is None:
            raise cls._bad("estimate_not_found", 404)
        return result[0], result[1]

    @classmethod
    async def get_revision(
        cls, session: AsyncSession, scope: TenantScope, estimate_id: int, revision: int,
    ) -> ManagerInstallationEstimateRevisionResponse:
        estimate, saved = await cls._revision(session, scope, estimate_id, revision)
        return ManagerInstallationEstimateRevisionResponse(
            **cls._confirm_response(estimate, saved).model_dump(), snapshot=saved.snapshot,
        )

    @classmethod
    def _projection(
        cls, saved: InstallationEstimateRevision, mode: str,
    ) -> tuple[list[tuple[str, Decimal]], Decimal]:
        result = InstallationPreviewResponse.model_validate(saved.snapshot["result"])
        return cls.project_preview(result, mode, expected_total=saved.total)

    @classmethod
    def project_preview(
        cls, result: InstallationPreviewResponse, mode: str, *, expected_total: Decimal | None = None,
    ) -> tuple[list[tuple[str, Decimal]], Decimal]:
        if result.status != "fixed" or result.total is None or result.subtotal is None or result.discount is None:
            raise cls._bad("invalid_estimate_snapshot")
        try:
            total = exact_money(result.total)
            subtotal = exact_money(result.subtotal)
            discount = exact_money(result.discount)
            gross = [exact_money(item.gross) for item in result.components]
            net = [exact_money(item.net) for item in result.components]
            reductions = [exact_money(item.discount) for item in result.components]
            if sum(gross, Decimal("0.00")) != subtotal or subtotal - discount != total \
               or sum(net, Decimal("0.00")) != total or sum(reductions, Decimal("0.00")) != discount \
               or any(item_gross != item_net + item_discount for item_gross, item_net, item_discount
                      in zip(gross, net, reductions)) or (expected_total is not None and total != exact_money(expected_total)):
                raise ValueError("Totals do not reconcile")
            if mode == "collapsed":
                if not result.customer_text:
                    raise ValueError("Customer text is missing")
                writable_service_money(total)
                return [(result.customer_text, total)], total
            summaries = {item.installation_key: item for item in result.installations}
            site_work = {item.code: item for item in result.site_work}
            detailed: list[tuple[str, Decimal]] = []
            for component, amount in zip(result.components, net):
                if component.installation_key is None:
                    selected = site_work.get(component.code)
                    label = (f"{selected.label}: {InstallationPriceBookService._quantity_text(selected.quantity)} "
                             f"{selected.unit}") if selected else None
                else:
                    summary = summaries.get(component.installation_key)
                    if summary is None:
                        raise ValueError("Installation summary is missing")
                    if component.code == "installation.base":
                        label = summary.work_label
                        included_work = [
                            f"{item.label.lower()} {InstallationPriceBookService._quantity_text(item.actual)} "
                            f"{item.unit} (включено {InstallationPriceBookService._quantity_text(item.included)} {item.unit})"
                            for item in summary.measured if item.extra == 0
                        ]
                        if included_work:
                            label += "; " + ", ".join(included_work)
                    elif component.code == "route.extra_m":
                        label = next((f"Дополнительная трасса {item.extra} м: фактически {item.actual} м, включено {item.included} м"
                                      for item in summary.measured if item.code == "route.length_m"), None)
                    elif component.code.startswith("hole."):
                        hole_code = component.code.removesuffix(".extra")
                        label = next((f"{item.label}: дополнительно {item.extra} шт, фактически {item.actual} шт, включено {item.included} шт"
                                      for item in summary.measured if item.code == hole_code), None)
                    else:
                        label = next((f"{item.label}: {InstallationPriceBookService._quantity_text(item.quantity)} {item.unit}"
                                      for item in summary.selected_extras
                                      if item.code == component.code), None)
                    if label:
                        label = f"Установка {summary.display_label or component.installation_key}: {label}"
                if not label:
                    raise ValueError("Component has no factual label")
                writable_service_money(amount)
                detailed.append((label, amount))
            if not detailed or sum((amount for _, amount in detailed), Decimal("0.00")) != total:
                raise ValueError("Detailed lines do not reconcile")
            return detailed, total
        except ValueError as exc:
            raise cls._bad("invalid_estimate_snapshot") from exc

    @classmethod
    async def attach(
        cls, session: AsyncSession, scope: TenantScope, *, order_id: int, proposal_id: int,
        estimate_id: int, payload: ManagerInstallationAttachPayload, idempotency_key: str,
    ) -> PublicWriteCommandOutcome[ManagerInstallationAttachResponse]:
        fingerprint = cls._fingerprint({"order_id": order_id, "proposal_id": proposal_id,
                                        "estimate_id": estimate_id, **payload.model_dump(mode="json")})

        async def operation() -> PublicWriteCommandResponse[ManagerInstallationAttachResponse]:
            order = await cls._order(session, scope, order_id)
            proposal = cls._proposal(order, proposal_id)
            estimate, saved = await cls._revision(session, scope, estimate_id, payload.revision)
            if estimate.order_id != order_id or estimate.proposal_id != proposal_id:
                raise cls._bad("estimate_not_found", 404)
            original_input = InstallationPreviewPayload.model_validate(saved.snapshot["input"])
            verified_keys = saved.snapshot.get("confirmation", {}).get("verified_service_only_keys", [])
            cls._verify_equipment(order, proposal_id, original_input, verified_keys)
            lines, total = cls._projection(saved, payload.mode)
            existing = list((await session.execute(select(OrderServiceLink).join(
                InstallationEstimateRevision,
                InstallationEstimateRevision.id == OrderServiceLink.installation_estimate_revision_id,
            ).where(
                OrderServiceLink.order_id == order_id,
                OrderServiceLink.proposal_id == proposal_id,
                InstallationEstimateRevision.estimate_id == estimate_id,
            ).order_by(OrderServiceLink.installation_line_index)) ).scalars())
            if existing:
                if len(existing) != len(lines) or any(
                    link.installation_estimate_revision_id != saved.id or
                    link.installation_projection_mode != payload.mode or
                    link.installation_line_index != index or link.quantity != 1 or
                    link.title != title or exact_money(link.price) != amount
                    for index, (link, (title, amount)) in enumerate(zip(existing, lines))
                ):
                    raise cls._bad("estimate_already_attached")
                persisted = existing
            else:
                cls._editable(proposal)
                try:
                    await cls.validate_attached_claims(session, order_id, proposal_id, incoming=original_input)
                except ValueError as exc:
                    raise cls._bad("installation_already_attached") from exc
                persisted = [OrderServiceLink(
                    order_id=order_id, proposal_id=proposal_id,
                    installation_estimate_revision_id=int(saved.id),
                    installation_line_index=index, installation_projection_mode=payload.mode,
                    service_id=None, quantity=1, title=title, price=amount, cost=Decimal("0.00"),
                ) for index, (title, amount) in enumerate(lines)]
                session.add_all(persisted)
                await session.flush()
                await OrderService._refresh_order_financials(session, order)
                session.add(order)
            response = ManagerInstallationAttachResponse(
                estimate_id=estimate_id, revision=payload.revision, order_id=order_id,
                proposal_id=proposal_id, mode=payload.mode, total=total,
                lines=[ManagerInstallationAttachedLine(link_id=int(link.id), title=link.title,
                                                       price=exact_money(link.price)) for link in persisted],
            )
            encoded = json.dumps(response.model_dump(mode="json"), ensure_ascii=False,
                                 sort_keys=True, separators=(",", ":")).encode("utf-8")
            if len(encoded) > cls.ATTACH_RESPONSE_MAX_BYTES:
                raise cls._bad("estimate_projection_too_large", 422)
            return PublicWriteCommandResponse(value=response, status_code=200,
                resource_type="installation_estimate", resource_id=estimate_id,
                response_max_bytes=cls.ATTACH_RESPONSE_MAX_BYTES)

        return await PublicWriteIdempotencyService.execute(
            session, tenant_scope=scope, command_name="manager_installation_attach_v1",
            idempotency_key=idempotency_key, request_fingerprint=fingerprint,
            response_model=ManagerInstallationAttachResponse, operation=operation,
        )
