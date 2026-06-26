from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import (
    Customer,
    CustomerBranch,
    CustomerType,
    DocumentRoleType,
    Installer,
    LeadSource,
    Order,
    OrderProductLink,
    OrderProposal,
    OrderServiceLink,
    OrderStageStatus,
    OrderStatus,
    OrderWorkStage,
    Payment,
    PaymentCurrency,
    PaymentType,
    Product,
    Service,
)
from models.common import EquipmentStatus
from schemas import (
    ManagerOrderExportRequest,
    ManagerOrderImportCommitRequest,
    ManagerOrderImportPreviewRequest,
    ManagerOrderImportPreviewResponse,
    ManagerOrderTransferCustomer,
    ManagerOrderTransferCustomerBranch,
    ManagerOrderTransferOrder,
    ManagerOrderTransferPackage,
    ManagerOrderTransferPayment,
    ManagerOrderTransferProductLine,
    ManagerOrderTransferProductRef,
    ManagerOrderTransferProposal,
    ManagerOrderTransferServiceLine,
    ManagerOrderTransferServiceRef,
    ManagerOrderTransferWorkStage,
)
from services.order_service import OrderService


@dataclass
class _ResolvedProduct:
    product: Optional[Product]
    status: str
    reason: Optional[str] = None


class OrderTransferService:
    """Export/import selected manager orders as a portable JSON package."""

    PACKAGE_VERSION = 1

    @staticmethod
    def _enum_value(value: Any) -> Any:
        return value.value if hasattr(value, "value") else value

    @staticmethod
    def _clean(value: Any) -> str:
        return " ".join(str(value or "").split())

    @staticmethod
    def _optional_clean(value: Any) -> Optional[str]:
        cleaned = OrderTransferService._clean(value)
        return cleaned or None

    @staticmethod
    def _parse_enum(enum_cls: Any, raw: Any, fallback: Any) -> Any:
        if raw is None or raw == "":
            return fallback
        if isinstance(raw, enum_cls):
            return raw
        try:
            return enum_cls(str(raw))
        except Exception as exc:
            raise ValueError(f"Invalid {enum_cls.__name__}: {raw}") from exc

    @staticmethod
    def _technical_meta_for_export(order: Order) -> dict[str, Any]:
        return order.technical_meta if isinstance(order.technical_meta, dict) else {}

    @staticmethod
    def _customer_snapshot(customer: Optional[Customer]) -> Optional[ManagerOrderTransferCustomer]:
        if not customer:
            return None
        return ManagerOrderTransferCustomer(
            source_id=customer.id,
            type=OrderTransferService._enum_value(customer.type) or CustomerType.individual.value,
            name=customer.name or "Без имени",
            phone=customer.phone or "",
            email=customer.email,
            full_legal_name=customer.full_legal_name,
            inn=customer.inn,
            legal_address=customer.legal_address,
            actual_address=customer.actual_address,
            bank_name=customer.bank_name,
            bic=customer.bic,
            iban=customer.iban,
        )

    @staticmethod
    def _branch_snapshot(branch: Optional[CustomerBranch]) -> Optional[ManagerOrderTransferCustomerBranch]:
        if not branch:
            return None
        return ManagerOrderTransferCustomerBranch(
            source_id=branch.id,
            name=branch.name,
            delivery_address=branch.delivery_address,
            contact_name=branch.contact_name,
            contact_phone=branch.contact_phone,
            is_default=bool(branch.is_default),
        )

    @staticmethod
    def _product_ref(link: OrderProductLink) -> ManagerOrderTransferProductRef:
        product = link.product
        return ManagerOrderTransferProductRef(
            source_id=product.id if product else link.product_id,
            title=product.title if product else f"Товар #{link.product_id}",
            slug=product.slug if product else None,
            source_url=product.source_url if product else None,
        )

    @staticmethod
    def _service_ref(link: OrderServiceLink) -> Optional[ManagerOrderTransferServiceRef]:
        if not link.service and not link.service_id:
            return None
        service = link.service
        return ManagerOrderTransferServiceRef(
            source_id=service.id if service else link.service_id,
            title=service.title if service else (link.title or f"Услуга #{link.service_id}"),
            slug=service.slug if service else None,
        )

    @staticmethod
    def _product_line_snapshot(link: OrderProductLink) -> ManagerOrderTransferProductLine:
        return ManagerOrderTransferProductLine(
            source_id=link.id,
            product=OrderTransferService._product_ref(link),
            quantity=int(link.quantity or 1),
            price=int(link.price or 0),
            cost=int(link.cost or 0),
            is_installation_included=bool(link.is_installation_included),
            installation_price=int(link.installation_price or 0),
            installation_details=link.installation_details,
            logistics_components=OrderService._serialize_order_logistics_components(link.logistics_components),
        )

    @staticmethod
    def _service_line_snapshot(link: OrderServiceLink) -> ManagerOrderTransferServiceLine:
        return ManagerOrderTransferServiceLine(
            source_id=link.id,
            service=OrderTransferService._service_ref(link),
            title=link.title or (link.service.title if link.service else f"Услуга #{link.service_id}"),
            quantity=int(link.quantity or 1),
            price=int(link.price or 0),
            cost=int(link.cost or 0),
        )

    @staticmethod
    def _proposal_snapshot(order: Order, proposal: OrderProposal) -> ManagerOrderTransferProposal:
        product_lines = [link for link in order.product_links if link.proposal_id == proposal.id]
        service_lines = [link for link in order.service_links if link.proposal_id == proposal.id]
        return ManagerOrderTransferProposal(
            source_id=proposal.id,
            name=proposal.name or "Основное",
            status=proposal.status or "draft",
            is_selected=bool(proposal.is_selected),
            is_archived=bool(proposal.is_archived),
            sort_order=int(proposal.sort_order or 0),
            product_lines=[OrderTransferService._product_line_snapshot(link) for link in product_lines],
            service_lines=[OrderTransferService._service_line_snapshot(link) for link in service_lines],
        )

    @staticmethod
    def _payment_snapshot(payment: Payment) -> ManagerOrderTransferPayment:
        return ManagerOrderTransferPayment(
            source_id=payment.id,
            amount=float(payment.amount or 0),
            currency=OrderTransferService._parse_enum(PaymentCurrency, payment.currency, PaymentCurrency.BYN),
            date=payment.date,
            type=OrderTransferService._enum_value(payment.type) or PaymentType.PREPAYMENT.value,
            comment=payment.comment,
        )

    @staticmethod
    def _work_stage_snapshot(stage: OrderWorkStage) -> ManagerOrderTransferWorkStage:
        return ManagerOrderTransferWorkStage(
            source_id=stage.id,
            name=stage.name,
            status=OrderTransferService._enum_value(stage.status) or OrderStageStatus.PLANNED.value,
            start_time=stage.start_time,
            end_time=stage.end_time,
            installer_name=stage.installer.name if stage.installer else None,
            manager_comment=stage.manager_comment,
            installer_report=stage.installer_report,
        )

    @staticmethod
    def _order_snapshot(
        order: Order,
        *,
        include_payments: bool,
        include_work_stages: bool,
    ) -> ManagerOrderTransferOrder:
        proposals = [
            OrderTransferService._proposal_snapshot(order, proposal)
            for proposal in sorted(order.proposals, key=lambda item: (item.is_archived, item.sort_order, item.id or 0))
        ]
        return ManagerOrderTransferOrder(
            source_id=order.id,
            status=OrderTransferService._enum_value(order.status) or OrderStatus.NEGOTIATION.value,
            lead_source=OrderTransferService._enum_value(order.lead_source) or LeadSource.MANAGER.value,
            title=order.title,
            workflow_type=OrderService._normalize_workflow_type(order.workflow_type),
            repair_meta=OrderService._get_repair_meta(order),
            manager_labels=OrderService._get_manager_labels(order),
            created_at=order.created_at,
            next_followup_date=order.next_followup_date,
            measurement_date=order.measurement_date,
            installation_date=order.installation_date,
            comment=order.comment,
            delivery_address=order.delivery_address,
            document_role_type=OrderTransferService._enum_value(order.document_role_type),
            additional_conditions=order.additional_conditions,
            closing_result=order.closing_result,
            reject_reason=order.reject_reason,
            is_on_hold=bool(order.is_on_hold),
            on_hold_reason=order.on_hold_reason,
            measurement_required=bool(order.measurement_required),
            measurement_result=order.measurement_result,
            negotiation_status=OrderService._infer_negotiation_status(order),
            negotiation_status_changed_at=getattr(order, "negotiation_status_changed_at", None),
            proposal_status=order.proposal_status or "draft",
            proposal_sent_at=order.proposal_sent_at,
            execution_without_payment=bool(getattr(order, "execution_without_payment", False)),
            execution_without_payment_reason=getattr(order, "execution_without_payment_reason", None),
            auto_execution_on_payment=bool(getattr(order, "auto_execution_on_payment", False)),
            auto_close_on_payment=bool(getattr(order, "auto_close_on_payment", False)),
            execution_status=OrderService._normalize_execution_status(getattr(order, "execution_status", None)),
            execution_status_changed_at=getattr(order, "execution_status_changed_at", None),
            equipment_status=OrderTransferService._enum_value(order.equipment_status) or EquipmentStatus.PENDING.value,
            standard_install_kit_issued=bool(order.standard_install_kit_issued),
            target_currency=order.target_currency,
            target_currency_amount=order.target_currency_amount,
            customer=OrderTransferService._customer_snapshot(order.customer),
            customer_branch=OrderTransferService._branch_snapshot(order.customer_branch),
            proposals=proposals,
            payments=[OrderTransferService._payment_snapshot(payment) for payment in order.payments] if include_payments else [],
            work_stages=[
                OrderTransferService._work_stage_snapshot(stage) for stage in order.work_stages
            ] if include_work_stages else [],
        )

    @staticmethod
    async def export_orders(session: AsyncSession, payload: ManagerOrderExportRequest) -> ManagerOrderTransferPackage:
        order_ids = list(dict.fromkeys(int(order_id) for order_id in payload.order_ids if int(order_id) > 0))
        if not order_ids:
            raise ValueError("No orders selected")

        stmt = (
            select(Order)
            .where(Order.id.in_(order_ids))
            .options(
                selectinload(Order.customer),
                selectinload(Order.customer_branch),
                selectinload(Order.proposals),
                selectinload(Order.product_links).selectinload(OrderProductLink.product),
                selectinload(Order.service_links).selectinload(OrderServiceLink.service),
                selectinload(Order.payments),
                selectinload(Order.work_stages).selectinload(OrderWorkStage.installer),
            )
            .execution_options(populate_existing=True)
        )
        result = await session.execute(stmt)
        orders = list(result.scalars().all())
        found_ids = {int(order.id or 0) for order in orders}
        missing_ids = [order_id for order_id in order_ids if order_id not in found_ids]
        if missing_ids:
            raise ValueError(f"Orders not found: {', '.join(str(item) for item in missing_ids)}")

        by_id = {int(order.id or 0): order for order in orders}
        sorted_orders = [by_id[order_id] for order_id in order_ids]
        for order in sorted_orders:
            await OrderService.ensure_default_proposal(session, order)

        return ManagerOrderTransferPackage(
            version=OrderTransferService.PACKAGE_VERSION,
            exported_at=datetime.now(),
            source="manager",
            orders=[
                OrderTransferService._order_snapshot(
                    order,
                    include_payments=payload.include_payments,
                    include_work_stages=payload.include_work_stages,
                )
                for order in sorted_orders
            ],
        )

    @staticmethod
    async def _find_customer(session: AsyncSession, customer_data: Optional[ManagerOrderTransferCustomer]) -> tuple[Optional[Customer], str]:
        if not customer_data:
            return None, "no_customer"

        inn = OrderTransferService._optional_clean(customer_data.inn)
        if inn:
            result = await session.execute(select(Customer).where(Customer.inn == inn).limit(1))
            customer = result.scalars().first()
            if customer:
                return customer, "matched_by_inn"

        phone = OrderTransferService._optional_clean(customer_data.phone)
        if phone:
            result = await session.execute(select(Customer).where(Customer.phone == phone).limit(1))
            customer = result.scalars().first()
            if customer:
                return customer, "matched_by_phone"

        email = OrderTransferService._optional_clean(customer_data.email)
        if email:
            result = await session.execute(select(Customer).where(func.lower(Customer.email) == email.lower()).limit(1))
            customer = result.scalars().first()
            if customer:
                return customer, "matched_by_email"

        return None, "will_create"

    @staticmethod
    async def _find_product(session: AsyncSession, product_ref: ManagerOrderTransferProductRef) -> _ResolvedProduct:
        slug = OrderTransferService._optional_clean(product_ref.slug)
        if slug:
            result = await session.execute(select(Product).where(Product.slug == slug).limit(1))
            product = result.scalars().first()
            if product:
                return _ResolvedProduct(product=product, status="matched", reason="slug")

        source_url = OrderTransferService._optional_clean(product_ref.source_url)
        if source_url:
            result = await session.execute(select(Product).where(Product.source_url == source_url).limit(1))
            product = result.scalars().first()
            if product:
                return _ResolvedProduct(product=product, status="matched", reason="source_url")

        title = OrderTransferService._optional_clean(product_ref.title)
        if title:
            result = await session.execute(
                select(Product)
                .where(func.lower(Product.title) == title.lower())
                .limit(2)
            )
            products = list(result.scalars().all())
            if len(products) == 1:
                return _ResolvedProduct(product=products[0], status="matched", reason="title")
            if len(products) > 1:
                return _ResolvedProduct(product=None, status="missing", reason="ambiguous_title")

        return _ResolvedProduct(product=None, status="missing", reason="not_found")

    @staticmethod
    async def _find_service(session: AsyncSession, service_ref: Optional[ManagerOrderTransferServiceRef]) -> Optional[Service]:
        if not service_ref:
            return None
        slug = OrderTransferService._optional_clean(service_ref.slug)
        if slug:
            result = await session.execute(select(Service).where(Service.slug == slug).limit(1))
            service = result.scalars().first()
            if service:
                return service
        title = OrderTransferService._optional_clean(service_ref.title)
        if title:
            result = await session.execute(select(Service).where(func.lower(Service.title) == title.lower()).limit(1))
            return result.scalars().first()
        return None

    @staticmethod
    async def preview_import(
        session: AsyncSession,
        payload: ManagerOrderImportPreviewRequest,
    ) -> ManagerOrderImportPreviewResponse:
        package = payload.package
        warnings: list[str] = []
        if package.version != OrderTransferService.PACKAGE_VERSION:
            warnings.append(f"Версия пакета {package.version}; текущая версия импорта {OrderTransferService.PACKAGE_VERSION}")

        customer_matches: list[dict[str, Any]] = []
        product_matches: list[dict[str, Any]] = []
        products_total = 0
        products_matched = 0

        for order_data in package.orders:
            customer, reason = await OrderTransferService._find_customer(session, order_data.customer)
            customer_matches.append(
                {
                    "source_order_id": order_data.source_id,
                    "customer_name": order_data.customer.name if order_data.customer else None,
                    "matched_customer_id": customer.id if customer else None,
                    "matched_customer_name": customer.name if customer else None,
                    "status": "matched" if customer else ("none" if not order_data.customer else "will_create"),
                    "reason": reason,
                }
            )

            for proposal in order_data.proposals:
                for product_line in proposal.product_lines:
                    products_total += 1
                    resolved = await OrderTransferService._find_product(session, product_line.product)
                    if resolved.product:
                        products_matched += 1
                    product_matches.append(
                        {
                            "source_order_id": order_data.source_id,
                            "product_title": product_line.product.title,
                            "product_slug": product_line.product.slug,
                            "matched_product_id": resolved.product.id if resolved.product else None,
                            "matched_product_title": resolved.product.title if resolved.product else None,
                            "status": resolved.status,
                            "reason": resolved.reason,
                        }
                    )

        products_missing = products_total - products_matched
        if products_missing:
            warnings.append("Есть товарные строки без найденного товара; импорт заблокирован до исправления каталога")

        return ManagerOrderImportPreviewResponse(
            orders_count=len(package.orders),
            products_total=products_total,
            products_matched=products_matched,
            products_missing=products_missing,
            customers=customer_matches,
            products=product_matches,
            can_import=products_missing == 0 and len(package.orders) > 0,
            warnings=warnings,
        )

    @staticmethod
    async def _get_or_create_customer(
        session: AsyncSession,
        customer_data: Optional[ManagerOrderTransferCustomer],
    ) -> Optional[Customer]:
        customer, _ = await OrderTransferService._find_customer(session, customer_data)
        if customer or not customer_data:
            return customer

        customer = Customer(
            name=customer_data.name or "Без имени",
            phone=customer_data.phone or "",
            email=customer_data.email,
            type=OrderTransferService._parse_enum(CustomerType, customer_data.type, CustomerType.individual),
            full_legal_name=customer_data.full_legal_name,
            inn=customer_data.inn,
            legal_address=customer_data.legal_address,
            actual_address=customer_data.actual_address,
            bank_name=customer_data.bank_name,
            bic=customer_data.bic,
            iban=customer_data.iban,
        )
        session.add(customer)
        await session.flush()
        return customer

    @staticmethod
    async def _get_or_create_branch(
        session: AsyncSession,
        customer: Optional[Customer],
        branch_data: Optional[ManagerOrderTransferCustomerBranch],
    ) -> Optional[CustomerBranch]:
        if not customer or not customer.id or not branch_data:
            return None
        result = await session.execute(
            select(CustomerBranch)
            .where(
                CustomerBranch.customer_id == customer.id,
                CustomerBranch.delivery_address == branch_data.delivery_address,
            )
            .limit(1)
        )
        branch = result.scalars().first()
        if branch:
            return branch
        branch = CustomerBranch(
            customer_id=int(customer.id),
            name=branch_data.name,
            delivery_address=branch_data.delivery_address,
            contact_name=branch_data.contact_name,
            contact_phone=branch_data.contact_phone,
            is_default=bool(branch_data.is_default),
        )
        session.add(branch)
        await session.flush()
        return branch

    @staticmethod
    def _build_import_meta(order_data: ManagerOrderTransferOrder) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "transfer_import": {
                "source_order_id": order_data.source_id,
                "imported_at": datetime.now().isoformat(),
            }
        }
        if order_data.manager_labels:
            meta[OrderService.MANAGER_LABELS_META_KEY] = order_data.manager_labels
        if order_data.repair_meta:
            meta[OrderService.REPAIR_META_KEY] = order_data.repair_meta
        return meta

    @staticmethod
    async def _find_installer_by_name(session: AsyncSession, name: Optional[str]) -> Optional[Installer]:
        cleaned = OrderTransferService._optional_clean(name)
        if not cleaned:
            return None
        result = await session.execute(select(Installer).where(func.lower(Installer.name) == cleaned.lower()).limit(1))
        return result.scalars().first()

    @staticmethod
    async def import_orders(session: AsyncSession, payload: ManagerOrderImportCommitRequest) -> dict[str, Any]:
        preview = await OrderTransferService.preview_import(
            session,
            ManagerOrderImportPreviewRequest(package=payload.package),
        )
        if not preview.can_import:
            raise ValueError("Import preview has unresolved products")

        created_order_ids: list[int] = []
        warnings: list[str] = []
        skipped_payments = 0

        for order_data in payload.package.orders:
            customer = await OrderTransferService._get_or_create_customer(session, order_data.customer)
            branch = await OrderTransferService._get_or_create_branch(session, customer, order_data.customer_branch)
            order = Order(
                customer_id=customer.id if customer else None,
                customer_branch_id=branch.id if branch else None,
                delivery_address=order_data.delivery_address or (branch.delivery_address if branch else None),
                document_role_type=OrderTransferService._parse_enum(DocumentRoleType, order_data.document_role_type, None)
                if order_data.document_role_type else None,
                status=OrderTransferService._parse_enum(OrderStatus, order_data.status, OrderStatus.NEGOTIATION),
                lead_source=OrderTransferService._parse_enum(LeadSource, order_data.lead_source, LeadSource.MANAGER),
                title=order_data.title,
                comment=order_data.comment,
                workflow_type=OrderService._normalize_workflow_type(order_data.workflow_type),
                technical_meta=OrderTransferService._build_import_meta(order_data),
                is_paid=False,
                target_currency=order_data.target_currency,
                target_currency_amount=order_data.target_currency_amount,
                closing_result=order_data.closing_result,
                reject_reason=order_data.reject_reason,
                is_on_hold=bool(order_data.is_on_hold),
                on_hold_reason=order_data.on_hold_reason,
                measurement_required=bool(order_data.measurement_required),
                measurement_date=order_data.measurement_date,
                measurement_result=order_data.measurement_result,
                additional_conditions=order_data.additional_conditions,
                negotiation_status=OrderService._normalize_negotiation_status(order_data.negotiation_status),
                negotiation_status_changed_at=order_data.negotiation_status_changed_at,
                proposal_status=order_data.proposal_status or "draft",
                proposal_sent_at=order_data.proposal_sent_at,
                execution_without_payment=bool(order_data.execution_without_payment),
                execution_without_payment_reason=order_data.execution_without_payment_reason,
                auto_execution_on_payment=bool(order_data.auto_execution_on_payment),
                auto_close_on_payment=bool(order_data.auto_close_on_payment),
                execution_status=OrderService._normalize_execution_status(order_data.execution_status),
                execution_status_changed_at=order_data.execution_status_changed_at,
                equipment_status=OrderTransferService._parse_enum(
                    EquipmentStatus,
                    order_data.equipment_status,
                    EquipmentStatus.PENDING,
                ),
                standard_install_kit_issued=bool(order_data.standard_install_kit_issued),
                created_at=order_data.created_at or datetime.now(),
                installation_date=order_data.installation_date,
                next_followup_date=order_data.next_followup_date,
                status_changed_at=order_data.created_at or datetime.now(),
            )
            session.add(order)
            await session.flush()

            active_proposals = [proposal for proposal in order_data.proposals if not proposal.is_archived]
            selected_source_id = next((proposal.source_id for proposal in active_proposals if proposal.is_selected), None)
            if selected_source_id is None and active_proposals:
                selected_source_id = active_proposals[0].source_id

            for index, proposal_data in enumerate(order_data.proposals or [ManagerOrderTransferProposal(name="Основное", is_selected=True)]):
                proposal = OrderProposal(
                    order_id=int(order.id),
                    name=proposal_data.name or "Основное",
                    status=proposal_data.status or "draft",
                    is_selected=proposal_data.source_id == selected_source_id or (selected_source_id is None and index == 0),
                    is_archived=bool(proposal_data.is_archived),
                    sort_order=int(proposal_data.sort_order or index * 10),
                )
                session.add(proposal)
                await session.flush()

                for product_line in proposal_data.product_lines:
                    resolved = await OrderTransferService._find_product(session, product_line.product)
                    if not resolved.product:
                        raise ValueError(f"Product not found: {product_line.product.title}")
                    session.add(
                        OrderProductLink(
                            order_id=int(order.id),
                            proposal_id=int(proposal.id),
                            product_id=int(resolved.product.id),
                            quantity=int(product_line.quantity or 1),
                            price=int(product_line.price or 0),
                            cost=int(product_line.cost or 0),
                            is_installation_included=bool(product_line.is_installation_included),
                            installation_price=int(product_line.installation_price or 0),
                            installation_details=product_line.installation_details,
                            logistics_components=[
                                item.model_dump() if hasattr(item, "model_dump") else dict(item)
                                for item in (product_line.logistics_components or [])
                            ] or None,
                        )
                    )

                for service_line in proposal_data.service_lines:
                    service = await OrderTransferService._find_service(session, service_line.service)
                    session.add(
                        OrderServiceLink(
                            order_id=int(order.id),
                            proposal_id=int(proposal.id),
                            service_id=service.id if service else None,
                            title=service_line.title,
                            quantity=int(service_line.quantity or 1),
                            price=int(service_line.price or 0),
                            cost=int(service_line.cost or 0),
                        )
                    )

            await session.flush()

            for payment_data in order_data.payments:
                try:
                    currency = OrderTransferService._parse_enum(PaymentCurrency, payment_data.currency, PaymentCurrency.BYN)
                    ptype = OrderTransferService._parse_enum(PaymentType, payment_data.type, PaymentType.PREPAYMENT)
                except ValueError:
                    skipped_payments += 1
                    warnings.append(f"Платеж из заказа #{order_data.source_id} пропущен: неизвестная валюта или тип")
                    continue
                session.add(
                    Payment(
                        order_id=int(order.id),
                        amount=float(payment_data.amount or 0),
                        currency=currency,
                        date=payment_data.date,
                        type=ptype,
                        comment=payment_data.comment,
                    )
                )

            for stage_data in order_data.work_stages:
                installer = await OrderTransferService._find_installer_by_name(session, stage_data.installer_name)
                session.add(
                    OrderWorkStage(
                        order_id=int(order.id),
                        name=stage_data.name,
                        status=OrderTransferService._parse_enum(OrderStageStatus, stage_data.status, OrderStageStatus.PLANNED),
                        start_time=stage_data.start_time,
                        end_time=stage_data.end_time,
                        installer_id=installer.id if installer else None,
                        manager_comment=stage_data.manager_comment,
                        installer_report=stage_data.installer_report,
                    )
                )

            await session.flush()
            await OrderService._refresh_order_financials(session, order)
            order.is_paid = bool(order.balance_due <= 0 and order.total_amount > 0)
            session.add(order)
            await session.flush()
            created_order_ids.append(int(order.id))

        await session.commit()
        return {
            "created_order_ids": created_order_ids,
            "created_count": len(created_order_ids),
            "skipped_payments": skipped_payments,
            "warnings": warnings,
        }
