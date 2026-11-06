"""Native chosen sales drafts, with atomic receipts and frozen tariff provenance."""

import hashlib
from dataclasses import replace
from decimal import Decimal

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import selectinload

from core.config import settings
from models import Order, OrderProductLink, OrderServiceLink
from modules.documents.application import DocumentContextSelection, ManagedDocumentService
from modules.documents.application.customer_readiness import check_saved_document_readiness
from schemas_connector_sales_order import (
    SalesCustomerResult, SalesOrderLine, SalesOrderOfferReadInput, SalesOrderOfferResult,
    SalesOrderReadInput, SalesOrderResult,
)
from services.authenticated_command_service import AuthenticatedCommandService
from services.catalog_decision_order_lines import CatalogDecisionOrderLineService
from services.catalog_decision_projection import CatalogDecisionQueryService
from services.connector_sales_pricing import ConnectorSalesPricingService
from services.connector_service_order_document import _issuer, _storage, _url
from services.customer_creation_service import CustomerAlreadyExistsError, CustomerCreationService
from services.installation_estimate_confirmation_service import InstallationEstimateConfirmationService as Confirmation
from services.installation_price_book_service import InstallationPriceBookService
from services.order_create_command_service import OrderCreateCommandService
from services.order_proposal_version import proposal_version
from services.order_sales_context_version import sales_order_context_version
from services.order_responsibility_service import OrderResponsibilityService
from services.order_service import OrderService
from services.public_catalog_visibility_service import PublicCatalogVisibilityService
from services.public_write_idempotency_service import PublicWriteCommandResponse
from services.tenant_entity_access_service import TenantEntityAccessService as Access
from schemas_manager_orders import ManagerOrderCreatePayload


class _SavedResource(BaseModel):
    id: int
    proposal_id: int | None = None


async def _order(session, actor, order_id):
    order = await Access.get_order(session, order_id, tenant_scope=actor.tenant_scope,
        options=(selectinload(Order.proposals),
                 selectinload(Order.product_links).selectinload(OrderProductLink.product),
                 selectinload(Order.service_links).selectinload(OrderServiceLink.service),
                 selectinload(Order.payments), selectinload(Order.installers)),
        for_update=True, populate_existing=True)
    if order is None:
        raise HTTPException(404, "Order not found")
    if order.workflow_type != "sales_installation" or (order.technical_meta or {}).get("service_type") != "turnkey":
        raise HTTPException(409, "Choose a sales and installation order")
    return order


def _proposal(order, proposal_id=None):
    proposal = next((p for p in order.proposals if not p.is_archived and
                     (p.id == proposal_id if proposal_id is not None else p.is_selected)), None)
    if proposal is None:
        raise HTTPException(404, "Proposal not found")
    return proposal


def _context(order, proposal_id):
    return ((order.technical_meta or {}).get("sales_selections") or {}).get(str(proposal_id))


async def _version(session, order, proposal):
    return await sales_order_context_version(session, order.id, proposal.id)


async def _access(session, actor, data):
    if await OrderResponsibilityService.initial_responsible(session, actor.tenant_scope, actor.staff_user_id) is None:
        raise HTTPException(403, "Active company staff membership required")
    if getattr(data, "customer_id", None) is not None:
        customer = await Access.get_customer(session, data.customer_id, tenant_scope=actor.tenant_scope)
        if customer is None or customer.is_archived:
            raise HTTPException(404, "Active customer not found")
    if getattr(data, "order_id", None) is not None:
        order = await Access.get_order(session, data.order_id, tenant_scope=actor.tenant_scope)
        if order is None:
            raise HTTPException(404, "Order not found")
        if getattr(data, "customer_id", None) is not None and order.customer_id != data.customer_id:
            raise HTTPException(404, "Order and customer not found together")


async def get_sales_order(session, actor, data):
    order = await _order(session, actor, data.order_id)
    proposal = _proposal(order, data.proposal_id)
    customer = await Access.get_customer(session, order.customer_id, tenant_scope=actor.tenant_scope)
    if customer is None or customer.is_archived:
        raise HTTPException(404, "Active customer not found")
    context = _context(order, proposal.id)
    products = [SalesOrderLine(id=p.id, product_id=p.product_id,
        title=p.title_snapshot or (p.product.title if p.product else "Товар"), quantity=p.quantity,
        unit_price_byn=Decimal(str(p.price)), total_byn=Decimal(str(p.price)) * p.quantity)
        for p in order.product_links if p.proposal_id == proposal.id]
    services = [SalesOrderLine(id=p.id, title=p.title or "Монтаж", quantity=p.quantity,
        unit_price_byn=Decimal(str(p.price)), total_byn=Decimal(str(p.price)) * p.quantity,
        installation_estimate_revision_id=p.installation_estimate_revision_id)
        for p in order.service_links if p.proposal_id == proposal.id]
    main_id = (context or {}).get("product_id")
    equipment = sum((p.total_byn for p in products if p.product_id == main_id), Decimal("0"))
    accessories = sum((p.total_byn for p in products if p.product_id != main_id), Decimal("0"))
    installation = sum((p.total_byn for p in services), Decimal("0"))
    return SalesOrderResult(order_id=order.id, customer_id=customer.id,
        customer_type=str(getattr(customer.type, "value", customer.type)), proposal_id=proposal.id,
        status=OrderService._status_value(order.status), proposal_status=proposal.status,
        workflow_type=order.workflow_type, service_type="turnkey", version=await _version(session, order, proposal),
        request_text=order.comment, requirements_text=(context or {}).get("requirements_text"),
        title=order.title, address=order.delivery_address, saved_selection=context,
        products=products, services=services, equipment_total_byn=equipment,
        accessories_total_byn=accessories, installation_total_byn=installation,
        total_byn=equipment + accessories + installation,
        manager_url=f"{settings.MANAGER_BASE_URL.rstrip('/')}/orders/kanban?orderId={order.id}&proposalId={proposal.id}")


async def save_sales_order(session, actor, data):
    actor = await ConnectorSalesPricingService.verified_actor(session, actor)
    scope = actor.tenant_scope
    # The live responsibility fence holds Tenant FOR SHARE until commit. This
    # already blocks tariff publication (NO KEY UPDATE); do not upgrade that
    # shared lock when concurrent managers save independent orders.
    await _access(session, actor, data)
    option = await ConnectorSalesPricingService.price_option(session, actor, product_id=data.product_id,
        installation=data.installation, accessory_product_ids=data.accessory_product_ids,
        expected_fingerprint=data.expected_calculation_fingerprint)
    if data.order_id is None:
        created = await OrderCreateCommandService.create_manager_order(session,
            ManagerOrderCreatePayload(customer_id=data.customer_id, source="manager", workflow_type="sales_installation",
                service_type="turnkey", request_text=data.request_text, title=data.title, address=data.address),
            tenant_scope=scope, creator_staff_user_id=actor.staff_user_id)
        order = await _order(session, actor, int(created["id"]))
        proposal = _proposal(order)
    else:
        order = await _order(session, actor, data.order_id)
        proposal = _proposal(order, data.proposal_id)
        if await _version(session, order, proposal) != data.expected_version:
            raise HTTPException(409, "Sales order changed; reload before editing")
        # Only this connector's chosen composition can be replaced as a whole.
        if _context(order, proposal.id) is None:
            raise HTTPException(409, "This proposal has no saved sales selection; edit it in Manager")
        if not proposal.is_selected:
            raise HTTPException(409, "Choose the current selected proposal in Manager before editing")
    if OrderService._status_value(order.status) != "negotiation" or proposal.status != "draft":
        raise HTTPException(409, "Sales selection requires a selected draft proposal in negotiation")
    canonical = await PublicCatalogVisibilityService.is_canonical_scope(session, scope)
    catalog_scope = replace(scope, is_system=canonical, is_canonical_storefront=canonical)
    ids = [data.product_id, *data.accessory_product_ids]
    snapshots = await CatalogDecisionQueryService.get_product_snapshots(session, tenant_scope=catalog_scope,
        product_ids=ids, allowed_accessory_ids=data.accessory_product_ids)
    if set(snapshots) != set(ids):
        raise HTTPException(404, "Selected products are no longer available")
    accepted_prices = {data.product_id: option.product.unit_price_byn,
                       **{item.product_id: item.price for item in option.selected_accessories}}
    if any(snapshots[pid].retail_price_byn != accepted_prices[pid] for pid in ids):
        raise HTTPException(409, "Catalog price changed; refresh the sales calculation")
    # Order product amounts are integer BYN in the native domain. Never silently
    # truncate a public quote while copying it into the order.
    if any(s.retail_price_byn != Decimal(str(s.retail_price_byn)).to_integral_value() for s in snapshots.values()):
        raise HTTPException(409, "This catalog price cannot be saved exactly in a native order; review in Manager")
    for line in list(order.service_links):
        if line.proposal_id == proposal.id:
            if line.installation_estimate_revision_id is None or (
                data.order_id is not None and line.installation_estimate_revision_id !=
                (_context(order, proposal.id) or {}).get("installation_estimate_revision_id")
            ):
                raise HTTPException(409, "Proposal contains other service lines; review it in Manager")
            await session.delete(line)
    await session.flush()
    await CatalogDecisionOrderLineService.replace(session, order_id=order.id, proposal_id=proposal.id,
                                                  product_ids=ids, snapshots=snapshots)
    await session.refresh(order, attribute_names=["product_links", "service_links"])
    payload = ConnectorSalesPricingService.preview_payload(data.product_id, data.installation)
    preview_key = hashlib.sha256(f"sales-preview:{actor.staff_user_id}:{data.idempotency_key}".encode()).hexdigest()
    preview = await InstallationPriceBookService.preview(session, scope, payload, idempotency_key=preview_key)
    row, _, result = await Confirmation.validated_fixed_preview(session, scope, preview.preview_ref)
    if result.model_dump(mode="json", exclude={"preview_ref", "expires_at"}) != option.installation.model_dump(
        mode="json", exclude={"preview_ref", "expires_at"}
    ):
        raise HTTPException(409, "Installation price changed; refresh the sales calculation")
    # Retain the exact accepted tariff bytes as a normal immutable domain revision.
    _, revision = await Confirmation.persist_revision(session, scope, row=row, result=result,
        order_id=order.id, proposal_id=proposal.id, key_hash=preview_key,
        request_hash=data.expected_calculation_fingerprint, actor=f"staff:{actor.staff_user_id}",
        verified_service_only_keys=[], group_commercial_lines=True)
    session.add_all(Confirmation.new_revision_lines(order_id=order.id, proposal_id=proposal.id,
                                                   saved=revision, mode="collapsed"))
    contexts = dict((order.technical_meta or {}).get("sales_selections") or {})
    contexts[str(proposal.id)] = dict(product_id=data.product_id,
        accessory_product_ids=data.accessory_product_ids, installation=data.installation.model_dump(mode="json"),
        calculation_fingerprint=option.calculation_fingerprint, requirements_text=data.requirements_text,
        installation_estimate_revision_id=revision.id)
    order.technical_meta = {**(order.technical_meta or {}), "sales_selections": contexts}
    order.comment, order.delivery_address = data.request_text, data.address
    if data.title is not None:
        order.title = OrderService._clean_order_title(data.title)
    order.workflow_revision += 1
    session.add(order)
    await session.flush()
    await session.refresh(order, attribute_names=["product_links", "service_links"])
    await OrderService._refresh_order_financials(session, order)
    await session.flush()
    return await get_sales_order(session, actor, SalesOrderReadInput(order_id=order.id, proposal_id=proposal.id))


async def _offer_result(session, actor, document, *, template_storage=None):
    meta = (document.render_snapshot or {}).get("meta") or {}
    version = meta.get("connector_proposal_version")
    if document.doc_type != "offer" or meta.get("connector_sales_offer") is not True or not version:
        raise HTTPException(404, "Sales offer not found")
    order = await _order(session, actor, document.order_id)
    _proposal(order, document.proposal_id)
    await _issuer(session, actor.tenant_scope, document.legal_entity_id)
    current = await proposal_version(session, order.id, document.proposal_id)
    saved_context_version = meta.get("sales_order_context_version")
    stale = version != current or (
        saved_context_version is not None
        and saved_context_version != await sales_order_context_version(session, order.id, document.proposal_id)
    )
    readiness = await check_saved_document_readiness(session, tenant_scope=actor.tenant_scope,
        document=document, template_storage=template_storage or _storage())
    return SalesOrderOfferResult(order_id=order.id, proposal_id=document.proposal_id, document_id=document.id,
        legal_entity_id=document.legal_entity_id, status=document.status, proposal_version=version,
        current_proposal_version=current, stale=stale,
        customer_ready_and_current=document.status == "draft" and not stale and readiness.get("can_issue", False),
        readiness=readiness, total_byn=str(((document.render_snapshot or {}).get("values") or {}).get("totals.amount", "")),
        manager_url=_url(order.id, document.proposal_id, document.id))


async def prepare_sales_order_offer(session, actor, data, *, template_storage=None):
    order = await _order(session, actor, data.order_id)
    proposal = _proposal(order, data.proposal_id)
    if OrderService._status_value(order.status) != "negotiation" or proposal.status != "draft" or not proposal.is_selected:
        raise HTTPException(409, "Choose the current sales draft proposal in negotiation")
    if await _version(session, order, proposal) != data.expected_version:
        raise HTTPException(409, "Sales order changed; reload before preparing its offer")
    if not any(p.proposal_id == proposal.id for p in order.product_links):
        raise HTTPException(409, "Add equipment to the selected proposal first")
    customer = await Access.get_customer(session, order.customer_id, tenant_scope=actor.tenant_scope)
    if customer is None or customer.is_archived:
        raise HTTPException(404, "Active customer not found")
    issuer = await _issuer(session, actor.tenant_scope, data.legal_entity_id)
    storage = template_storage or _storage()
    version = await proposal_version(session, order.id, proposal.id)
    document = await ManagedDocumentService.create_draft(session, tenant_scope=actor.tenant_scope,
        selection=DocumentContextSelection(order_id=order.id, proposal_id=proposal.id, legal_entity_id=issuer.id,
            document_type="offer", issue_date=data.issue_date), template_id=data.template_id,
        template_storage=storage, commit=False)
    snapshot = dict(document.render_snapshot)
    snapshot["meta"] = {**(snapshot.get("meta") or {}), "connector_proposal_version": version,
                        "connector_sales_offer": True,
                        "sales_order_context_version": await _version(session, order, proposal)}
    document.render_snapshot = snapshot
    session.add(document)
    await session.flush()
    return await _offer_result(session, actor, document, template_storage=storage)


async def get_sales_order_offer(session, actor, data, *, template_storage=None):
    document = await ManagedDocumentService.get_document(session, tenant_scope=actor.tenant_scope,
                                                          document_id=data.document_id)
    return await _offer_result(session, actor, document, template_storage=template_storage)


async def create_sales_customer(session, actor, data):
    try:
        customer = await CustomerCreationService.create_record_for_manager(session,
            payload=data.customer.model_dump(exclude_none=True), tenant_scope=actor.tenant_scope)
    except CustomerAlreadyExistsError as exc:
        raise HTTPException(409, {"code": "customer_already_exists", "customer_id": exc.customer_id,
                                  "matched_fields": list(exc.matched_fields)}) from exc
    return SalesCustomerResult(customer_id=customer.id, name=customer.name,
        customer_type=str(getattr(customer.type, "value", customer.type)),
        manager_url=f"{settings.MANAGER_BASE_URL.rstrip('/')}/customers?customerId={customer.id}")


async def execute_sales_order_tool(session, actor, name, inputs):
    if name == "get_sales_order":
        return await get_sales_order(session, actor, inputs)
    if name == "get_sales_order_offer":
        return await get_sales_order_offer(session, actor, inputs)
    await _access(session, actor, inputs)
    result = None

    async def operation():
        nonlocal result
        if name == "create_sales_customer":
            result = await create_sales_customer(session, actor, inputs)
            return PublicWriteCommandResponse(result, resource_type="customer", resource_id=result.customer_id)
        if name == "save_sales_order":
            result = await save_sales_order(session, actor, inputs)
            value = _SavedResource(id=result.order_id, proposal_id=result.proposal_id)
            kind = "order"
        elif name == "prepare_sales_order_offer":
            result = await prepare_sales_order_offer(session, actor, inputs)
            value, kind = _SavedResource(id=result.document_id), "order_document"
        else:
            raise ValueError("Unknown sales order tool")
        return PublicWriteCommandResponse(value, resource_type=kind, resource_id=value.id)

    outcome = await AuthenticatedCommandService.execute(session, actor=actor, command_name=name,
        idempotency_key=inputs.idempotency_key, payload=inputs.model_dump(mode="json", exclude={"idempotency_key"}),
        response_model=SalesCustomerResult if name == "create_sales_customer" else _SavedResource, operation=operation)
    if outcome.replayed:
        if name == "create_sales_customer":
            result = outcome.value
            customer = await Access.get_customer(session, result.customer_id, tenant_scope=actor.tenant_scope)
            if customer is None or customer.is_archived:
                raise HTTPException(404, "Active customer not found")
        elif name == "save_sales_order":
            result = await get_sales_order(session, actor, SalesOrderReadInput(order_id=outcome.value.id,
                                                                              proposal_id=outcome.value.proposal_id))
        else:
            result = await get_sales_order_offer(session, actor, SalesOrderOfferReadInput(document_id=outcome.value.id))
    return {"result": result, "replayed": outcome.replayed}
