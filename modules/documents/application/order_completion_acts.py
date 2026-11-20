"""Create an idempotent, site-scoped draft in the standard completion-act lifecycle."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.command_actor import CommandActor
from core.config import settings
from models import OrderProposal, OrderStatus
from modules.documents.domain import ActTerms
from modules.documents.infrastructure.template_source_storage import TemplateSourceStorage
from schemas_order_completion_acts import (
    OrderCompletionActPrepared,
    OrderCompletionActSource,
    OrderCompletionActSourceInput,
    PrepareOrderCompletionActInput,
)
from services.authenticated_command_service import AuthenticatedCommandService
from services.customer_party import is_business_customer_type
from services.order_proposal_version import proposal_version
from services.public_write_idempotency_service import PublicWriteCommandResponse
from services.tenant_entity_access_service import TenantEntityAccessService

from .context_builder import DocumentContextSelection
from .draft_parameters import draft_revision
from .errors import ManagedDocumentConflictError, ManagedDocumentNotFoundError
from .lifecycle_service import ManagedDocumentService
from .order_completion_coverage import CompletionActScope, validate_scoped_act_capacity


async def _order(session, scope, order_id, *, lock=False):
    order = await TenantEntityAccessService.get_order(
        session, order_id, tenant_scope=scope, for_update=lock, populate_existing=True,
    )
    if order is None:
        raise ManagedDocumentNotFoundError("Заказ не найден")
    return order


async def _version(session, order_id: int, proposal_id: int) -> str:
    proposal = await session.scalar(select(OrderProposal).where(
        OrderProposal.id == proposal_id, OrderProposal.order_id == order_id,
    ).execution_options(populate_existing=True))
    if proposal is None:
        raise ManagedDocumentNotFoundError("Предложение заказа не найдено")
    if proposal.is_archived or not proposal.is_selected or proposal.status == "rejected":
        raise ManagedDocumentConflictError("Выберите действующее основное предложение заказа")
    return await proposal_version(session, order_id, proposal_id)


async def _validate_replacement_revision(session, actor: CommandActor, data: PrepareOrderCompletionActInput) -> None:
    if data.replaces_document_id is None:
        return
    source = await ManagedDocumentService.get_document(
        session, tenant_scope=actor.tenant_scope, document_id=data.replaces_document_id,
    )
    if source.order_id != data.order_id or source.doc_type != "act":
        raise ManagedDocumentNotFoundError("Заменяемый акт не найден")
    artifacts = await ManagedDocumentService.list_artifacts(
        session, tenant_scope=actor.tenant_scope, document_id=source.id,
    )
    if draft_revision(source, artifacts) != data.expected_document_revision:
        raise ManagedDocumentConflictError("Акт изменился. Прочитайте его актуальную версию.")


class OrderCompletionActService:
    @staticmethod
    async def source(
        session: AsyncSession, actor: CommandActor, data: OrderCompletionActSourceInput,
    ) -> OrderCompletionActSource:
        await _order(session, actor.tenant_scope, data.order_id)
        version = await _version(session, data.order_id, data.proposal_id)
        return OrderCompletionActSource(order_id=data.order_id, proposal_id=data.proposal_id, proposal_version=version)

    @staticmethod
    async def prepare(
        session: AsyncSession, actor: CommandActor, data: PrepareOrderCompletionActInput, *,
        template_storage: TemplateSourceStorage,
    ):
        from services.order_site_service import OrderSiteService

        tenant_scope = actor.tenant_scope
        await _order(session, tenant_scope, data.order_id)

        async def create_draft() -> PublicWriteCommandResponse[OrderCompletionActPrepared]:
            order = await _order(session, tenant_scope, data.order_id, lock=True)
            if order.status == OrderStatus.CLOSED:
                raise ManagedDocumentConflictError("Заказ завершён: документы доступны только для просмотра")
            customer = (
                await TenantEntityAccessService.get_customer(session, order.customer_id, tenant_scope=tenant_scope)
                if order.customer_id else None
            )
            if customer is None or customer.is_archived or not is_business_customer_type(customer.type):
                raise ManagedDocumentConflictError("Для общего акта выберите активного заказчика-организацию или ИП")
            version = await _version(session, data.order_id, data.proposal_id)
            if version != data.expected_proposal_version:
                raise ManagedDocumentConflictError("Предложение изменилось. Прочитайте его актуальную версию.")
            sites = []
            for site_id in data.site_ids:
                site, _ = await OrderSiteService.resolve_scope(session, tenant_scope, data.order_id, site_id, (), lock=True)
                sites.append(site)
            scope = CompletionActScope(tuple(sites), version)
            await _validate_replacement_revision(session, actor, data)
            document = await ManagedDocumentService.create_draft(
                session, tenant_scope=tenant_scope, selection=DocumentContextSelection(
                    order_id=data.order_id, document_type="act", legal_entity_id=data.legal_entity_id,
                    issue_date=data.issue_date, issue_city=data.issue_city,
                    document_role_type=data.document_role_type.value if data.document_role_type else None,
                    proposal_id=data.proposal_id, base_document_id=data.base_document_id,
                    base_customer_contract_id=data.base_customer_contract_id,
                    scope_customer_branch_id=sites[0].customer_branch_id if len(sites) == 1 else None,
                    scope_title=scope.title, scope_address=scope.printable_address,
                    scope_service_line_ids=tuple(data.scope_service_line_ids),
                    scope_service_line_quantities=data.scope_service_line_quantities,
                    scope_product_line_ids=tuple(data.scope_product_line_ids),
                    scope_product_line_quantities=data.scope_product_line_quantities,
                    act_terms=ActTerms(**data.act_terms.model_dump()), completion_act_scope=scope,
                ),
                template_id=data.template_id, replaces_document_id=data.replaces_document_id,
                template_storage=template_storage, commit=False,
            )
            await validate_scoped_act_capacity(session, document)
            result = OrderCompletionActPrepared(
                order_id=data.order_id, site_ids=scope.site_ids, proposal_id=data.proposal_id,
                document_id=document.id, status=document.status, revision=draft_revision(document),
                manager_url=f"{settings.MANAGER_BASE_URL.rstrip('/')}/orders/{data.order_id}?section=documents&documentId={document.id}",
            )
            return PublicWriteCommandResponse(result, resource_type="order_document", resource_id=document.id)

        outcome = await AuthenticatedCommandService.execute(
            session, actor=actor, command_name="order_completion_act.prepare", idempotency_key=data.idempotency_key,
            payload=data.model_dump(mode="json", exclude={"idempotency_key"}),
            response_model=OrderCompletionActPrepared, operation=create_draft,
        )
        if outcome.replayed:
            await ManagedDocumentService.get_document(session, tenant_scope=tenant_scope, document_id=outcome.value.document_id)
        return outcome
