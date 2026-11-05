"""Link reusable customer contracts to their issuer and issued native source."""

import sqlalchemy as sa
from alembic import op

revision = "doc20261105reg01"
down_revision = "doc20261105act01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("customer_contract", sa.Column("legal_entity_id", sa.Integer()))
    op.add_column("customer_contract", sa.Column("source_document_id", sa.Integer()))
    op.create_foreign_key("fk_customer_contract_issuer", "customer_contract", "document_legal_entity",
                          ["legal_entity_id"], ["id"])
    op.create_foreign_key("fk_customer_contract_source_document", "customer_contract", "order_document",
                          ["source_document_id"], ["id"], ondelete="RESTRICT")
    op.create_check_constraint("ck_customer_contract_source_issuer", "customer_contract",
                               "source_document_id IS NULL OR legal_entity_id IS NOT NULL")
    op.create_unique_constraint("uq_customer_contract_source_document", "customer_contract", ["source_document_id"])
    op.create_index("ix_customer_contract_legal_entity_id", "customer_contract", ["legal_entity_id"])


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM customer_contract "
                                    "WHERE source_document_id IS NOT NULL OR legal_entity_id IS NOT NULL)")):
        raise RuntimeError("Нельзя удалить привязки использованного реестра договоров")
    op.drop_index("ix_customer_contract_legal_entity_id", table_name="customer_contract")
    op.drop_constraint("ck_customer_contract_source_issuer", "customer_contract", type_="check")
    op.drop_constraint("uq_customer_contract_source_document", "customer_contract", type_="unique")
    op.drop_constraint("fk_customer_contract_source_document", "customer_contract", type_="foreignkey")
    op.drop_constraint("fk_customer_contract_issuer", "customer_contract", type_="foreignkey")
    op.drop_column("customer_contract", "source_document_id")
    op.drop_column("customer_contract", "legal_entity_id")
