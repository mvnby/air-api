import pytest

from models import (
    Customer,
    CustomerType,
    Order,
    OrderProductLink,
    OrderProposal,
    OrderServiceLink,
    OrderStatus,
    Product,
    Service,
)
from services.document_service import DocumentService


@pytest.mark.asyncio
@pytest.mark.parametrize("doc_type", ["contract", "invoice"])
async def test_contract_and_invoice_only_render_selected_proposal_lines(db, monkeypatch, doc_type):
    customer = Customer(
        tenant_id=1,
        name="Proposal document customer",
        phone="+375296660279",
        type=CustomerType.individual,
    )
    cheap_product = Product(
        title="Cheap selected conditioner",
        slug=f"cheap-selected-conditioner-{doc_type}",
        price=1000,
    )
    expensive_product = Product(
        title="Expensive alternative conditioner",
        slug=f"expensive-alternative-conditioner-{doc_type}",
        price=2000,
    )
    installation = Service(
        title="Selected installation",
        slug=f"selected-installation-{doc_type}",
        base_price=100,
    )
    db.add_all([customer, cheap_product, expensive_product, installation])
    await db.flush()

    order = Order(
        tenant_id=1,
        storefront_id=1,
        customer_id=customer.id,
        status=OrderStatus.NEGOTIATION,
        total_amount=1100,
        total_cost=760,
        margin=340,
    )
    db.add(order)
    await db.flush()

    selected_proposal = OrderProposal(
        order_id=order.id,
        name="Selected cheap option",
        is_selected=True,
        sort_order=0,
    )
    alternative_proposal = OrderProposal(
        order_id=order.id,
        name="Expensive alternative",
        is_selected=False,
        sort_order=1,
    )
    db.add_all([selected_proposal, alternative_proposal])
    await db.flush()

    db.add_all(
        [
            OrderProductLink(
                order_id=order.id,
                proposal_id=selected_proposal.id,
                product_id=cheap_product.id,
                quantity=1,
                price=1000,
                cost=700,
            ),
            OrderServiceLink(
                order_id=order.id,
                proposal_id=selected_proposal.id,
                service_id=installation.id,
                title=installation.title,
                quantity=1,
                price=100,
                cost=60,
            ),
            OrderProductLink(
                order_id=order.id,
                proposal_id=alternative_proposal.id,
                product_id=expensive_product.id,
                quantity=1,
                price=2000,
                cost=1300,
            ),
        ]
    )
    await db.commit()

    captured_tables = []

    class FakeGoogleService:
        creds = object()

        def copy_template(self, template_id, title):
            return {
                "file_id": f"selected-proposal-{doc_type}",
                "edit_url": f"https://docs.google.com/document/d/selected-proposal-{doc_type}/edit",
            }

        def replace_placeholders(self, file_id, replacements):
            return None

        def _fill_table(self, docs_service, file_id, table_data, has_footer):
            captured_tables.append(table_data)

        def delete_file(self, file_id):
            return None

    from services import document_service
    import googleapiclient.discovery

    monkeypatch.setattr(document_service, "get_google_service", lambda: FakeGoogleService())
    monkeypatch.setattr(googleapiclient.discovery, "build", lambda *args, **kwargs: object())

    document = await DocumentService._create_new_document(
        db,
        order_id=order.id,
        doc_type=doc_type,
    )

    assert document.proposal_id == selected_proposal.id
    assert captured_tables == [
        [
            ["1", cheap_product.title, "шт.", "1", "1000.00", "1000.00"],
            ["2", installation.title, "шт.", "1", "100.00", "100.00"],
            ["Всего:", "", "", "", "", "1100.00"],
        ]
    ]
    assert expensive_product.title not in str(captured_tables)


def test_contract_and_invoice_line_scope_does_not_change_document_reuse_policy():
    assert {"contract", "invoice"} <= DocumentService.PROPOSAL_LINE_SCOPED_DOC_TYPES
    assert {"contract", "invoice"}.isdisjoint(DocumentService.PROPOSAL_SCOPED_DOC_TYPES)
