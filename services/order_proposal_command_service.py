"""Transactional commands for Manager order proposals.

Every public command owns exactly one database transaction.  Mutation helpers
may flush so later steps can use generated identifiers, but they never commit
or roll back independently.
"""

from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import Order, OrderMultiSplitConfiguration, OrderProductLink, OrderProposal, OrderServiceLink
from services.command_transaction import command_transaction
from services.order_projection_service import OrderProjectionService
from services.order_proposal_lifecycle import (
    PROPOSAL_STATUS_READY,
    normalize_proposal_status,
    sync_selected_proposal_status,
)
from services.order_service import OrderService
from services.tenant_entity_access_service import TenantEntityAccessService
from services.tenant_scope_service import TenantScope


class OrderProposalCommandService:
    @staticmethod
    async def _load_order_for_write(
        session: AsyncSession,
        order_id: int,
        *,
        tenant_scope: TenantScope,
    ) -> Order:
        order = await TenantEntityAccessService.get_order(
            session,
            order_id,
            tenant_scope=tenant_scope,
            options=(
                selectinload(Order.proposals),
                selectinload(Order.product_links).selectinload(OrderProductLink.product),
                selectinload(Order.service_links).selectinload(OrderServiceLink.service),
                selectinload(Order.payments),
                selectinload(Order.installers),
            ),
            for_update=True,
            populate_existing=True,
        )
        if not order:
            raise ValueError("Order not found")
        await OrderService.ensure_default_proposal(session, order)
        return order

    @staticmethod
    async def ensure_default_order_proposal(
        session: AsyncSession,
        order_id: int,
        *,
        tenant_scope: TenantScope,
    ) -> None:
        """Persist a legacy default before its ID is returned to the editor."""
        if tenant_scope.demo_read_only:
            return
        async with command_transaction(session):
            await OrderProposalCommandService._load_order_for_write(
                session, order_id, tenant_scope=tenant_scope,
            )

    @staticmethod
    async def _project_committed_order(
        session: AsyncSession,
        order_id: int,
        *,
        tenant_scope: TenantScope,
    ) -> Dict[str, Any]:
        data = await OrderProjectionService.get_order_detail_for_manager(
            session,
            order_id,
            tenant_scope=tenant_scope,
        )
        if data is None:
            raise RuntimeError("Committed order is no longer visible in its tenant scope")
        return data

    @staticmethod
    async def create_order_proposal(
        session: AsyncSession,
        order_id: int,
        payload: Any,
        *,
        tenant_scope: TenantScope,
    ) -> Dict[str, Any]:
        async with command_transaction(session):
            order = await OrderProposalCommandService._load_order_for_write(
                session,
                order_id,
                tenant_scope=tenant_scope,
            )
            source = None
            source_id = getattr(payload, "duplicate_from_proposal_id", None)
            if source_id:
                source = next(
                    (
                        proposal
                        for proposal in order.proposals
                        if proposal.id == source_id and not proposal.is_archived
                    ),
                    None,
                )
                if not source:
                    raise ValueError("Source proposal not found")

            active_count = len(
                [proposal for proposal in order.proposals if not proposal.is_archived]
            )
            proposal = OrderProposal(
                order_id=order_id,
                name=OrderService._clean_proposal_name(
                    getattr(payload, "name", None),
                    f"Вариант {active_count + 1}",
                ),
                status="draft",
                is_selected=active_count == 0,
                sort_order=active_count * 10,
            )
            session.add(proposal)
            await session.flush()

            if source:
                source_configuration = (await session.execute(
                    select(OrderMultiSplitConfiguration).where(OrderMultiSplitConfiguration.proposal_id == source.id)
                )).scalar_one_or_none()
                if source_configuration is not None:
                    session.add(OrderMultiSplitConfiguration(
                        order_id=order_id,
                        proposal_id=int(proposal.id),
                        rooms=source_configuration.rooms,
                        component_snapshot=source_configuration.component_snapshot,
                        verification_status=source_configuration.verification_status,
                        profile_id=source_configuration.profile_id,
                        profile_version=source_configuration.profile_version,
                        source_url=source_configuration.source_url,
                        source_version=source_configuration.source_version,
                    ))
                for link in [
                    item for item in order.product_links if item.proposal_id == source.id
                ]:
                    session.add(
                        OrderProductLink(
                            order_id=order_id,
                            proposal_id=proposal.id,
                            product_id=link.product_id,
                            quantity=link.quantity,
                            price=link.price,
                            title_snapshot=link.title_snapshot,
                            client_description=link.client_description,
                            currency_snapshot=link.currency_snapshot,
                            cost=link.cost,
                            is_installation_included=link.is_installation_included,
                            installation_price=link.installation_price,
                            installation_details=link.installation_details,
                            logistics_components=OrderService._serialize_order_logistics_components(
                                link.logistics_components
                            ),
                        )
                    )
                from services.installation_estimate_projection import frozen_installation_presentations
                from services.order_service_description import service_line_description
                source_service_links = [
                    item for item in order.service_links if item.proposal_id == source.id
                ]
                presentations = await frozen_installation_presentations(session, source_service_links)
                for link in source_service_links:
                    session.add(
                        OrderServiceLink(
                            order_id=order_id,
                            proposal_id=proposal.id,
                            service_id=link.service_id,
                            title=link.title,
                            description=service_line_description(link, presentations.get(link.id)),
                            quantity=link.quantity,
                            price=link.price,
                            cost=link.cost,
                            installation_estimate_revision_id=link.installation_estimate_revision_id,
                            installation_line_index=link.installation_line_index,
                            installation_projection_mode=link.installation_projection_mode,
                        )
                    )
            await session.flush()
            await OrderService._refresh_order_financials(session, order)
            session.add(order)

        return await OrderProposalCommandService._project_committed_order(
            session,
            order_id,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def update_order_proposal(
        session: AsyncSession,
        order_id: int,
        proposal_id: int,
        payload: Any,
        *,
        tenant_scope: TenantScope,
    ) -> Dict[str, Any]:
        async with command_transaction(session):
            order = await OrderProposalCommandService._load_order_for_write(
                session,
                order_id,
                tenant_scope=tenant_scope,
            )
            proposal = next(
                (item for item in order.proposals if item.id == proposal_id),
                None,
            )
            if not proposal:
                raise ValueError("Proposal not found")
            fields_set = getattr(payload, "model_fields_set", None)
            if fields_set is None:
                fields_set = getattr(payload, "__fields_set__", set())
            from services.maintenance_commercial_guard import guard_proposal
            await guard_proposal(session, order_id, proposal_id, status=getattr(payload, "status", None), archiving=bool(getattr(payload, "is_archived", False)))
            if "name" in fields_set:
                proposal.name = OrderService._clean_proposal_name(
                    payload.name,
                    proposal.name,
                )
            status_changed = "status" in fields_set and payload.status is not None
            if status_changed:
                next_status = normalize_proposal_status(payload.status)
                if next_status == PROPOSAL_STATUS_READY:
                    product_links = [
                        link
                        for link in order.product_links
                        if link.proposal_id == proposal.id
                    ]
                    service_links = [
                        link
                        for link in order.service_links
                        if link.proposal_id == proposal.id
                    ]
                    total_amount, _, _ = OrderService._proposal_line_totals(
                        product_links,
                        service_links,
                    )
                    if not product_links and not service_links:
                        raise ValueError(
                            "Proposal must contain at least one line before it is ready to send"
                        )
                    if total_amount <= 0:
                        raise ValueError(
                            "Proposal total must be greater than zero before it is ready to send"
                        )
                proposal.status = next_status
            if "sort_order" in fields_set and payload.sort_order is not None:
                proposal.sort_order = int(payload.sort_order)
            if "is_archived" in fields_set and payload.is_archived is not None:
                proposal.is_archived = bool(payload.is_archived)
                if proposal.is_archived and proposal.is_selected:
                    active = [
                        item
                        for item in order.proposals
                        if item.id != proposal.id and not item.is_archived
                    ]
                    replacement = next(
                        iter(sorted(active, key=lambda item: item.sort_order)),
                        None,
                    )
                    proposal.is_selected = False
                    if replacement:
                        replacement.is_selected = True
                        replacement.status = normalize_proposal_status(
                            replacement.status
                        )
                        sync_selected_proposal_status(order, replacement)
                        session.add(replacement)
            session.add(proposal)
            if status_changed:
                sync_selected_proposal_status(order, proposal)
            await session.flush()
            await OrderService._refresh_order_financials(session, order)
            session.add(order)

        return await OrderProposalCommandService._project_committed_order(
            session,
            order_id,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def select_order_proposal(
        session: AsyncSession,
        order_id: int,
        proposal_id: int,
        *,
        tenant_scope: TenantScope,
    ) -> Dict[str, Any]:
        async with command_transaction(session):
            order = await OrderProposalCommandService._load_order_for_write(
                session,
                order_id,
                tenant_scope=tenant_scope,
            )
            proposal = next(
                (
                    item
                    for item in order.proposals
                    if item.id == proposal_id and not item.is_archived
                ),
                None,
            )
            if not proposal:
                raise ValueError("Proposal not found")
            from services.maintenance_commercial_guard import guard_proposal
            await guard_proposal(session, order_id, proposal_id, selecting=True)
            for item in order.proposals:
                item.is_selected = item.id == proposal.id
                session.add(item)
            proposal.status = normalize_proposal_status(proposal.status)
            sync_selected_proposal_status(order, proposal)
            await session.flush()
            await OrderService._refresh_order_financials(session, order)
            session.add(order)

        return await OrderProposalCommandService._project_committed_order(
            session,
            order_id,
            tenant_scope=tenant_scope,
        )
