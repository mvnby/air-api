"""Atomic, attributed catalog proposal + native document draft preparation."""

from dataclasses import replace

from fastapi import HTTPException
from sqlmodel import select

from core.config import settings
from models import Customer, DocumentLegalEntity, Order, OrderProposal
from modules.documents.application import DocumentContextSelection, ManagedDocumentService
from modules.documents.application.errors import ManagedDocumentConflictError
from modules.documents.infrastructure.template_source_storage import PrivateTemplateSourceStorage
from schemas_connector_catalog import CatalogDocumentResult, CatalogIssuer, CatalogIssuersResult, CatalogProductInput
from services.authenticated_command_service import AuthenticatedCommandService
from services.catalog_decision_order_lines import CatalogDecisionOrderLineService
from services.catalog_decision_projection import CatalogDecisionQueryService
from services.order_proposal_command_service import OrderProposalCommandService
from services.order_service import OrderService
from services.public_catalog_visibility_service import PublicCatalogVisibilityService
from services.public_write_idempotency_service import PublicWriteCommandResponse
from services.private_attachment_storage_service import get_private_attachment_storage
from services.tenant_entity_access_service import TenantEntityAccessService


class ConnectorCatalogDocumentService:
    @staticmethod
    async def list_issuers(session, actor):
        rows = (await session.execute(select(DocumentLegalEntity).where(
            DocumentLegalEntity.tenant_id == actor.tenant_scope.tenant_id,
            DocumentLegalEntity.status == "active",
        ).order_by(DocumentLegalEntity.is_default.desc(), DocumentLegalEntity.id).limit(100))).scalars().all()
        return CatalogIssuersResult(items=[CatalogIssuer(legal_entity_id=row.id,
            display_name=row.display_name, is_default=row.is_default) for row in rows])

    @staticmethod
    async def _context(session, actor, inputs):
        scope = actor.tenant_scope
        order = (await session.execute(select(Order.id, Order.customer_id).outerjoin(Customer, Customer.id == Order.customer_id).where(
            Order.id == inputs.order_id, TenantEntityAccessService.order_clause(scope),
            TenantEntityAccessService.order_customer_clause(scope),
        ))).one_or_none()
        customer = await TenantEntityAccessService.get_customer(session, inputs.customer_id, tenant_scope=scope)
        issuer = await session.get(DocumentLegalEntity, inputs.legal_entity_id)
        if order is None or customer is None or order.customer_id != customer.id:
            raise HTTPException(404, "Order and customer not found together")
        if issuer is None or issuer.tenant_id != scope.tenant_id or issuer.status != "active":
            raise HTTPException(404, "Active document issuer not found")
        # Preserve the actual CRM party type; model arguments cannot change it.
        party_type = str(customer.type.value if hasattr(customer.type, "value") else customer.type)
        if party_type not in {"company", "individual_entrepreneur"} or customer.is_archived:
            raise HTTPException(409, "Choose an active company or entrepreneur customer for a business document")
        return order

    @classmethod
    async def prepare(cls, session, actor, inputs, *, template_storage=None):
        from services.connector_catalog_selection_service import ConnectorCatalogSelectionService

        scope = actor.tenant_scope
        template_storage = template_storage or PrivateTemplateSourceStorage(get_private_attachment_storage())
        # Revalidate live source access even when returning a durable receipt.
        await cls._context(session, actor, inputs)
        for line in inputs.lines:
            await ConnectorCatalogSelectionService.get_product(session, actor, CatalogProductInput(product_id=line.product_id))
        request = inputs.model_dump(mode="json", exclude={"idempotency_key"})

        async def operation():
            order = await OrderProposalCommandService._load_order_for_write(session, inputs.order_id, tenant_scope=scope)
            await cls._context(session, actor, inputs)
            if OrderService._status_value(order.status) != "negotiation":
                raise ManagedDocumentConflictError("Catalog drafts require an order in negotiation")
            canonical = await PublicCatalogVisibilityService.is_canonical_scope(session, scope)
            catalog_scope = replace(scope, is_system=canonical, is_canonical_storefront=canonical)
            ids = [line.product_id for line in inputs.lines]
            snapshots = await CatalogDecisionQueryService.get_product_snapshots(session,
                tenant_scope=catalog_scope, product_ids=ids)
            if set(snapshots) != set(ids):
                raise HTTPException(404, "Selected products are no longer available in this catalog")
            for line in inputs.lines:
                await ConnectorCatalogSelectionService.get_product(session, actor, CatalogProductInput(product_id=line.product_id))
                snapshot = snapshots[line.product_id]
                if snapshot.retail_price_byn <= 0 or snapshot.retail_price_byn != line.expected_unit_price_byn:
                    raise ManagedDocumentConflictError("Catalog price changed; refresh selection before preparing the document")
            proposal = OrderProposal(order_id=order.id, name="Подбор из ChatGPT", status="draft",
                is_selected=False, sort_order=max((p.sort_order for p in order.proposals), default=0) + 10)
            session.add(proposal)
            await session.flush()
            await CatalogDecisionOrderLineService.append(session, order_id=order.id, proposal_id=proposal.id,
                product_ids=ids, snapshots=snapshots, quantities={line.product_id: line.quantity for line in inputs.lines})
            # The order was loaded before these rows existed. Refresh its scoped
            # collections so the native snapshot sees precisely the new variant.
            await session.refresh(order, attribute_names=["proposals", "product_links"])
            document = await ManagedDocumentService.create_draft(session, tenant_scope=scope,
                selection=DocumentContextSelection(order_id=order.id, document_type=inputs.document_type,
                    legal_entity_id=inputs.legal_entity_id, issue_date=inputs.issue_date, proposal_id=proposal.id,
                    business_role="payment_request" if inputs.document_type == "invoice" else None),
                template_id=inputs.template_id, template_storage=template_storage, commit=False)
            result = CatalogDocumentResult(order_id=order.id, customer_id=inputs.customer_id,
                proposal_id=proposal.id, document_id=document.id, document_type=inputs.document_type,
                equipment_total_byn=sum(line.expected_unit_price_byn * line.quantity for line in inputs.lines),
                manager_url=f"{settings.MANAGER_BASE_URL.rstrip('/')}/orders/kanban?orderId={order.id}")
            return PublicWriteCommandResponse(value=result, resource_type="order_document", resource_id=document.id)

        return await AuthenticatedCommandService.execute(session, actor=actor,
            command_name="catalog.prepare_document", idempotency_key=inputs.idempotency_key,
            payload=request, response_model=CatalogDocumentResult, operation=operation)
