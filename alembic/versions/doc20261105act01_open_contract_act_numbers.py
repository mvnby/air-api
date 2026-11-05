"""Retain printed open-contract act numbers separately from CRM identities."""

from alembic import op
import sqlalchemy as sa

revision = "doc20261105act01"
down_revision = "mail20261023rel01"
branch_labels = None
depends_on = None


def upgrade():
    # A nullable counter distinguishes a historical series awaiting confirmation.
    # No number is inferred or assigned to a historical document at migration.
    op.add_column("customer_contract", sa.Column("last_act_number", sa.Integer()))
    op.add_column("customer_contract", sa.Column(
        "act_number_confirmation_pending", sa.Boolean(), nullable=False, server_default=sa.false()
    ))
    op.create_check_constraint(
        "ck_customer_contract_last_act_number", "customer_contract", "last_act_number >= 0"
    )
    op.add_column("order_document", sa.Column("contract_act_number", sa.Integer()))
    op.create_check_constraint(
        "ck_order_document_contract_act_number", "order_document",
        "contract_act_number IS NULL OR (contract_act_number > 0 "
        "AND base_customer_contract_id IS NOT NULL AND doc_type = 'act')",
    )
    op.create_index(
        "uq_order_document_contract_act_number", "order_document",
        ["base_customer_contract_id", "contract_act_number"], unique=True,
        postgresql_where=sa.text("contract_act_number IS NOT NULL"),
    )


def downgrade():
    # Removing live numbering state would allow already-printed numbers to be reused.
    has_numbers = op.get_bind().execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM customer_contract WHERE last_act_number IS NOT NULL)"
        " OR EXISTS (SELECT 1 FROM order_document WHERE contract_act_number IS NOT NULL)"
    )).scalar_one()
    if has_numbers:
        raise RuntimeError("Нельзя удалить историю нумерации актов по открытым договорам")
    op.drop_index("uq_order_document_contract_act_number", table_name="order_document")
    op.drop_constraint("ck_order_document_contract_act_number", "order_document", type_="check")
    op.drop_column("order_document", "contract_act_number")
    op.drop_constraint("ck_customer_contract_last_act_number", "customer_contract", type_="check")
    op.drop_column("customer_contract", "act_number_confirmation_pending")
    op.drop_column("customer_contract", "last_act_number")
