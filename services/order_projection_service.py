"""Read-side projections for Manager order views.

This module owns query composition and response mapping.  OrderService keeps
thin compatibility delegates while command extraction proceeds in later
behavior-preserving slices.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import String, and_, cast, func, not_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import (
    Customer,
    CustomerBranch,
    CustomerType,
    Order,
    OrderInstaller,
    OrderProductLink,
    OrderProposal,
    OrderServiceLink,
    OrderStatus,
    OrderWorkStage,
    Payment,
)
from services.customer_contract_service import CustomerContractService
from services.document_role_service import DocumentRoleService
from services.order_service import OrderService
from services.tenant_entity_access_service import TenantEntityAccessService
from services.tenant_scope_service import TenantScope, tenant_scope_clause


class OrderProjectionService:
    @staticmethod
    def _map_customer_brief(customer: Optional[Customer]) -> Optional[Dict[str, Any]]:
        if not customer:
            return None
        return {
            "id": int(customer.id or 0),
            "type": customer.type.value if hasattr(customer.type, "value") else str(customer.type or CustomerType.individual.value),
            "name": customer.name or "Без имени",
            "phone": customer.phone or "",
            "email": customer.email,
            "full_legal_name": customer.full_legal_name,
            "inn": customer.inn,
            "legal_address": customer.legal_address,
            "bank_name": customer.bank_name,
            "bic": customer.bic,
            "iban": customer.iban,
            "signer_position": customer.signer_position,
            "signer_name": customer.signer_name,
            "acting_basis": customer.acting_basis,
        }

    @staticmethod
    def _map_customer_branch_brief(branch: Optional[CustomerBranch]) -> Optional[Dict[str, Any]]:
        if not branch:
            return None
        return {
            "id": int(branch.id or 0),
            "name": branch.name,
            "delivery_address": branch.delivery_address,
            "contact_name": branch.contact_name,
            "contact_phone": branch.contact_phone,
            "is_default": bool(branch.is_default),
        }

    @staticmethod
    def _map_order_list_item(order: Order) -> Dict[str, Any]:
        if (
            "proposals" in getattr(order, "__dict__", {})
            and "product_links" in getattr(order, "__dict__", {})
            and "service_links" in getattr(order, "__dict__", {})
        ):
            order.calculate_totals()
        return {
            "id": int(order.id or 0),
            "status": order.status.value if hasattr(order.status, "value") else str(order.status or OrderStatus.NEW_LEAD.value),
            "lead_source": (
                order.lead_source.value
                if order.lead_source and hasattr(order.lead_source, "value")
                else (str(order.lead_source) if order.lead_source else None)
            ),
            "title": OrderService._display_order_title(order),
            "workflow_type": OrderService._normalize_workflow_type(getattr(order, "workflow_type", None)),
            "repair_meta": OrderService._get_repair_meta(order),
            "manager_labels": OrderService._get_manager_labels(order),
            "created_at": order.created_at,
            "updated_at": order.updated_at,
            "status_changed_at": getattr(order, "status_changed_at", None),
            "next_followup_date": order.next_followup_date,
            "measurement_date": order.measurement_date,
            "installation_date": order.installation_date,
            "total_amount": float(order.total_amount or 0),
            "total_cost": float(order.total_cost or 0),
            "margin": float(order.margin or 0),
            "total_payments": float(order.total_payments or 0),
            "balance_due": float(order.balance_due or 0),
            "is_paid": bool(order.is_paid),
            "comment": order.comment,
            "delivery_address": order.delivery_address,
            "customer_contract_id": order.customer_contract_id,
            "document_role_type": (
                order.document_role_type.value if hasattr(order.document_role_type, "value") else order.document_role_type
            ),
            "effective_document_role_type": DocumentRoleService.effective_role_type(order),
            "additional_conditions": order.additional_conditions,
            "closing_result": order.closing_result,
            "reject_reason": order.reject_reason,
            "is_on_hold": bool(order.is_on_hold),
            "on_hold_reason": order.on_hold_reason,
            "measurement_required": bool(order.measurement_required),
            "measurer_id": order.measurer_id,
            "measurement_result": order.measurement_result,
            "negotiation_status": OrderService._infer_negotiation_status(order),
            "negotiation_status_changed_at": getattr(order, "negotiation_status_changed_at", None),
            "proposal_status": order.proposal_status or "draft",
            "proposal_sent_at": order.proposal_sent_at,
            "execution_without_payment": bool(getattr(order, "execution_without_payment", False)),
            "execution_without_payment_reason": getattr(order, "execution_without_payment_reason", None),
            "auto_execution_on_payment": bool(getattr(order, "auto_execution_on_payment", False)),
            "auto_close_on_payment": bool(getattr(order, "auto_close_on_payment", False)),
            "execution_status": OrderService._infer_execution_status(order),
            "execution_status_changed_at": getattr(order, "execution_status_changed_at", None),
            "equipment_status": getattr(order.equipment_status, "value", str(order.equipment_status)) if order.equipment_status else "pending",
            "standard_install_kit_issued": bool(order.standard_install_kit_issued),
            "target_currency": order.target_currency,
            "target_currency_amount": float(order.target_currency_amount) if order.target_currency_amount is not None else None,
            "target_currency_payments": float(order.target_currency_payments) if order.target_currency_payments is not None else 0.0,
            "customer": OrderProjectionService._map_customer_brief(order.customer),
            "customer_branch": OrderProjectionService._map_customer_branch_brief(order.customer_branch),
            "customer_contract": CustomerContractService.to_order_brief(order.customer_contract),
            "installer_id": order.installers[0].installer_id if getattr(order, "installers", None) else None,
            "installer": {
                "id": order.installers[0].installer.id,
                "name": order.installers[0].installer.name,
                "is_active": order.installers[0].installer.is_active,
                "default_rate": order.installers[0].installer.default_rate,
                "telegram_id": order.installers[0].installer.telegram_id,
            } if getattr(order, "installers", None) and getattr(order.installers[0], "installer", None) else None,
        }

    @staticmethod
    def _map_product_line(link: OrderProductLink) -> Dict[str, Any]:
        product_title = (
            getattr(link, "title_snapshot", None)
            or (link.product.title if link.product else f"Товар #{link.product_id}")
        )
        line_total = link.price * link.quantity
        return {
            "id": link.id,
            "proposal_id": link.proposal_id,
            "product_id": link.product_id,
            "product_title": product_title,
            "title_snapshot": getattr(link, "title_snapshot", None),
            "currency_snapshot": getattr(link, "currency_snapshot", None),
            "quantity": link.quantity,
            "price": link.price,
            "cost": link.cost,
            "is_installation_included": bool(link.is_installation_included),
            "installation_price": int(link.installation_price or 0),
            "line_total": line_total,
            "product_country": OrderService._extract_product_country(link.product),
            "product_logistics_components": OrderService._serialize_product_logistics_components(link.product),
            "logistics_components": OrderService._serialize_order_logistics_components(link.logistics_components) or [],
        }

    @staticmethod
    def _map_service_line(link: OrderServiceLink) -> Dict[str, Any]:
        service_title = link.title or (link.service.title if link.service else f"Услуга #{link.service_id}")
        line_total = link.price * link.quantity
        return {
            "id": link.id,
            "proposal_id": link.proposal_id,
            "service_id": link.service_id,
            "service_title": service_title,
            "service_category": link.service.category if link.service else None,
            "quantity": link.quantity,
            "price": link.price,
            "cost": link.cost,
            "line_total": line_total,
        }

    @staticmethod
    def _map_order_proposal(order: Order, proposal: OrderProposal) -> Dict[str, Any]:
        product_links = [link for link in order.product_links if link.proposal_id == proposal.id]
        service_links = [link for link in order.service_links if link.proposal_id == proposal.id]
        total_amount, total_cost, margin = OrderService._proposal_line_totals(product_links, service_links)
        return {
            "id": int(proposal.id),
            "order_id": int(proposal.order_id),
            "name": proposal.name,
            "status": proposal.status or "draft",
            "is_selected": bool(proposal.is_selected),
            "is_archived": bool(proposal.is_archived),
            "sort_order": int(proposal.sort_order or 0),
            "total_amount": total_amount,
            "total_cost": total_cost,
            "margin": margin,
            "product_lines": [OrderProjectionService._map_product_line(link) for link in product_links],
            "service_lines": [OrderProjectionService._map_service_line(link) for link in service_links],
        }

    @staticmethod
    async def get_orders_for_manager(
        session: AsyncSession,
        customer_segment: str,
        page: int,
        limit: int,
        *,
        tenant_scope: TenantScope,
        status: Optional[str] = None,
        search: Optional[str] = None,
        overdue_only: bool = False,
        sort: str = "created_at_desc",
    ) -> Dict[str, Any]:
        from schemas import Meta

        segment = customer_segment.lower()
        if segment not in {"all", "b2c", "b2b"}:
            raise ValueError(f"Invalid segment: {customer_segment}")

        # B2B = explicit business party OR customer has non-empty INN.
        # B2C = everything else (including legacy orders without linked customer).
        has_inn = and_(Customer.inn.is_not(None), func.length(func.trim(Customer.inn)) > 0)
        is_b2b = or_(
            cast(Customer.type, String).in_(
                (
                    CustomerType.company.value,
                    CustomerType.individual_entrepreneur.value,
                )
            ),
            has_inn,
        )
        base_filters = [
            TenantEntityAccessService.order_clause(tenant_scope),
            Order.status != OrderStatus.NEW_LEAD,
            or_(
                Order.customer_id.is_(None),
                tenant_scope_clause(Customer, tenant_scope),
            ),
        ]
        if segment == "b2b":
            base_filters.append(is_b2b)
        elif segment == "b2c":
            base_filters.append(or_(Customer.id.is_(None), not_(is_b2b)))

        base_stmt = (
            select(Order)
            .outerjoin(Customer, Order.customer_id == Customer.id)
            .options(
                selectinload(Order.customer),
                selectinload(Order.customer_branch),
                selectinload(Order.customer_contract),
                selectinload(Order.proposals),
                selectinload(Order.product_links).selectinload(OrderProductLink.product),
                selectinload(Order.service_links).selectinload(OrderServiceLink.service),
                selectinload(Order.installers).selectinload(OrderInstaller.installer),
            )
            .where(*base_filters)
        )

        count_stmt = (
            select(func.count(Order.id))
            .outerjoin(Customer, Order.customer_id == Customer.id)
            .where(*base_filters)
        )

        if status:
            try:
                status_enum = OrderStatus(status)
                base_stmt = base_stmt.where(Order.status == status_enum)
                count_stmt = count_stmt.where(Order.status == status_enum)
            except ValueError as exc:
                raise ValueError(f"Invalid status: {status}") from exc

        if search and search.strip():
            search_text = search.strip()
            like = f"%{search_text}%"
            technical_meta_search = or_(
                *[
                    cast(Order.technical_meta, String).ilike(f"%{variant}%")
                    for variant in OrderService._json_text_search_variants(search_text)
                ]
            )
            search_clause = or_(
                Customer.name.ilike(like),
                Customer.phone.ilike(like),
                Customer.full_legal_name.ilike(like),
                Customer.inn.ilike(like),
                Order.title.ilike(like),
                technical_meta_search,
                cast(Order.id, String).ilike(like),
            )
            base_stmt = base_stmt.where(search_clause)
            count_stmt = count_stmt.where(search_clause)

        if overdue_only:
            now = datetime.now()
            base_stmt = base_stmt.where(
                Order.next_followup_date.is_not(None),
                Order.next_followup_date < now,
            )
            count_stmt = count_stmt.where(
                Order.next_followup_date.is_not(None),
                Order.next_followup_date < now,
            )

        sort_map = {
            "created_at_desc": Order.created_at.desc(),
            "created_at_asc": Order.created_at.asc(),
            "updated_at_desc": Order.updated_at.desc(),
            "updated_at_asc": Order.updated_at.asc(),
            "followup_asc": Order.next_followup_date.asc().nullslast(),
            "followup_desc": Order.next_followup_date.desc().nullslast(),
            "margin_desc": Order.margin.desc(),
            "margin_asc": Order.margin.asc(),
        }
        order_by = sort_map.get(sort, Order.created_at.desc())
        base_stmt = base_stmt.order_by(order_by).offset((page - 1) * limit).limit(limit)

        total_result = await session.execute(count_stmt)
        total = int(total_result.scalar() or 0)

        result = await session.execute(base_stmt)
        orders = list(result.scalars().all())
        items = [OrderProjectionService._map_order_list_item(order) for order in orders]

        pages = (total + limit - 1) // limit if limit > 0 else 0
        return {
            "items": items,
            "meta": Meta(total=total, page=page, limit=limit, pages=pages),
        }

    @staticmethod
    async def get_order_detail_for_manager(
        session: AsyncSession,
        order_id: int,
        *,
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        order = await TenantEntityAccessService.get_order(
            session,
            order_id,
            tenant_scope=tenant_scope,
            options=(
                selectinload(Order.customer),
                selectinload(Order.customer_branch),
                selectinload(Order.customer_contract),
                selectinload(Order.proposals),
                selectinload(Order.product_links).selectinload(OrderProductLink.product),
                selectinload(Order.service_links).selectinload(OrderServiceLink.service),
                selectinload(Order.installers).selectinload(OrderInstaller.installer),
                selectinload(Order.documents),
                selectinload(Order.payments).selectinload(Payment.bank_receipt),
                selectinload(Order.work_stages).selectinload(OrderWorkStage.installer),
            ),
            populate_existing=True,
        )
        if not order:
            return None
        if order.customer_id is not None:
            owned_customer_id = (
                await session.execute(
                    select(Customer.id).where(
                        Customer.id == order.customer_id,
                        tenant_scope_clause(
                            Customer,
                            tenant_scope,
                        ),
                    )
                )
            ).scalar_one_or_none()
            if owned_customer_id is None:
                return None
        # Transitional compatibility: a legacy detail read may still repair a
        # missing default proposal.  The command-handler slice will move this
        # mutation out of the projection transaction without changing output.
        await OrderService.ensure_default_proposal(session, order)

        data = OrderProjectionService._map_order_list_item(order)
        from models import CustomerEquipment, EquipmentOrderLink
        from services.service_attachment_service import ServiceAttachmentService

        data["attachment_count"] = await ServiceAttachmentService.order_attachment_count(
            session,
            order=order,
            tenant_scope=tenant_scope,
        )
        linked_equipment_result = await session.execute(
            select(EquipmentOrderLink.equipment_id)
            .join(
                CustomerEquipment,
                CustomerEquipment.id == EquipmentOrderLink.equipment_id,
            )
            .join(Customer, Customer.id == CustomerEquipment.customer_id)
            .where(
                EquipmentOrderLink.order_id == order_id,
                tenant_scope_clause(Customer, tenant_scope),
            )
        )
        linked_equipment_ids = {int(value) for value in linked_equipment_result.scalars().all()}
        source_equipment_result = await session.execute(
            select(CustomerEquipment.id)
            .join(Customer, Customer.id == CustomerEquipment.customer_id)
            .where(
                CustomerEquipment.source_order_id == order_id,
                CustomerEquipment.is_archived == False,
                tenant_scope_clause(Customer, tenant_scope),
            )
        )
        linked_equipment_ids.update(int(value) for value in source_equipment_result.scalars().all())
        data["linked_equipment_count"] = len(linked_equipment_ids)
        selected_proposal = OrderService._selected_proposal(order)
        selected_proposal_id = selected_proposal.id if selected_proposal else None
        data["product_lines"] = [
            OrderProjectionService._map_product_line(link)
            for link in order.product_links
            if selected_proposal_id is None or link.proposal_id == selected_proposal_id
        ]
        data["service_lines"] = [
            OrderProjectionService._map_service_line(link)
            for link in order.service_links
            if selected_proposal_id is None or link.proposal_id == selected_proposal_id
        ]
        data["proposals"] = [
            OrderProjectionService._map_order_proposal(order, proposal)
            for proposal in sorted(order.proposals, key=lambda proposal: (proposal.is_archived, proposal.sort_order, proposal.id or 0))
        ]
        from services.document_service import DocumentService

        basis_lookup = await DocumentService.build_document_basis_lookup(session, list(order.documents))
        data["documents"] = []
        for doc in sorted(order.documents, key=lambda d: d.created_at, reverse=True):
            data["documents"].append(
                {
                    "id": doc.id,
                    "proposal_id": doc.proposal_id,
                    **basis_lookup.get(doc.id, {}),
                    "doc_type": doc.doc_type,
                    "number": doc.number,
                    "date": doc.date,
                    "edit_url": doc.google_edit_url,
                    "is_downloadable": bool(doc.google_file_id),
                }
            )
        data["payments"] = [OrderService._map_payment(p) for p in sorted(order.payments, key=lambda d: d.date, reverse=True)]
        data["work_stages"] = [
            {
                "id": ws.id,
                "order_id": ws.order_id,
                "name": ws.name,
                "status": ws.status.value if hasattr(ws.status, "value") else str(ws.status),
                "start_time": ws.start_time,
                "end_time": ws.end_time,
                "installer_id": ws.installer_id,
                "manager_comment": ws.manager_comment,
                "installer_report": ws.installer_report,
                "installer": {
                    "id": ws.installer.id,
                    "name": ws.installer.name,
                    "is_active": ws.installer.is_active,
                    "default_rate": ws.installer.default_rate,
                    "telegram_id": ws.installer.telegram_id,
                } if ws.installer else None,
            }
            for ws in (order.work_stages or [])
        ]
        return data
