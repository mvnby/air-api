"""contract tenant provenance after the reviewed MVN backfill

Revision ID: c9e0f1a2b3d4
Revises: b8d9e0f1a2c3
Create Date: 2026-07-31
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision = "c9e0f1a2b3d4"
down_revision = "b8d9e0f1a2c3"
branch_labels = None
depends_on = None


STOREFRONT_SCOPE_UNIQUE = "uq_storefront_id_tenant"
CUSTOMER_SCOPE_UNIQUE = "uq_customer_id_tenant"
ORDER_SCOPE_UNIQUE = "uq_order_id_tenant_storefront"

LEAD_STOREFRONT_SCOPE_FK = "fk_lead_storefront_tenant"
LEAD_CONVERTED_ORDER_SCOPE_FK = "fk_lead_converted_order_scope"
ORDER_STOREFRONT_SCOPE_FK = "fk_order_storefront_tenant"
ORDER_CUSTOMER_SCOPE_FK = "fk_order_customer_tenant"
REQUISITES_DUPLICATE_CUSTOMER_SCOPE_FK = (
    "fk_customer_requisites_duplicate_customer_tenant"
)
REQUISITES_CONFIRMED_CUSTOMER_SCOPE_FK = (
    "fk_customer_requisites_confirmed_customer_tenant"
)

LEAD_FINGERPRINT_INDEX = "uq_lead_bot_source_fingerprint"
ORDER_FINGERPRINT_INDEX = "uq_order_source_fingerprint"
REQUISITES_TELEGRAM_INDEX = "uq_customer_requisites_telegram_message"


CONTRACT_PREFLIGHTS: tuple[tuple[str, str], ...] = (
    (
        "customer_null_tenant",
        "SELECT COUNT(*) FROM customer WHERE tenant_id IS NULL",
    ),
    (
        "requisites_null_tenant",
        "SELECT COUNT(*) FROM customer_requisites_recognition "
        "WHERE tenant_id IS NULL",
    ),
    (
        "lead_null_scope",
        "SELECT COUNT(*) FROM lead "
        "WHERE tenant_id IS NULL OR storefront_id IS NULL",
    ),
    (
        "order_null_scope",
        'SELECT COUNT(*) FROM "order" '
        "WHERE tenant_id IS NULL OR storefront_id IS NULL",
    ),
    (
        "lead_storefront_tenant_mismatch",
        "SELECT COUNT(*) FROM lead AS item "
        "LEFT JOIN storefront AS scope "
        "ON scope.id = item.storefront_id "
        "AND scope.tenant_id = item.tenant_id "
        "WHERE scope.id IS NULL",
    ),
    (
        "order_storefront_tenant_mismatch",
        'SELECT COUNT(*) FROM "order" AS item '
        "LEFT JOIN storefront AS scope "
        "ON scope.id = item.storefront_id "
        "AND scope.tenant_id = item.tenant_id "
        "WHERE scope.id IS NULL",
    ),
    (
        "order_customer_tenant_mismatch",
        'SELECT COUNT(*) FROM "order" AS item '
        "LEFT JOIN customer AS owner "
        "ON owner.id = item.customer_id "
        "AND owner.tenant_id = item.tenant_id "
        "WHERE item.customer_id IS NOT NULL AND owner.id IS NULL",
    ),
    (
        "lead_converted_order_scope_mismatch",
        "SELECT COUNT(*) FROM lead AS item "
        'LEFT JOIN "order" AS converted '
        "ON converted.id = item.converted_order_id "
        "AND converted.tenant_id = item.tenant_id "
        "AND converted.storefront_id = item.storefront_id "
        "WHERE item.converted_order_id IS NOT NULL AND converted.id IS NULL",
    ),
    (
        "requisites_duplicate_customer_tenant_mismatch",
        "SELECT COUNT(*) FROM customer_requisites_recognition AS item "
        "LEFT JOIN customer AS duplicate_customer "
        "ON duplicate_customer.id = item.duplicate_customer_id "
        "AND duplicate_customer.tenant_id = item.tenant_id "
        "WHERE item.duplicate_customer_id IS NOT NULL "
        "AND duplicate_customer.id IS NULL",
    ),
    (
        "requisites_confirmed_customer_tenant_mismatch",
        "SELECT COUNT(*) FROM customer_requisites_recognition AS item "
        "LEFT JOIN customer AS confirmed_customer "
        "ON confirmed_customer.id = item.confirmed_customer_id "
        "AND confirmed_customer.tenant_id = item.tenant_id "
        "WHERE item.confirmed_customer_id IS NOT NULL "
        "AND confirmed_customer.id IS NULL",
    ),
    (
        "duplicate_tenant_lead_fingerprint",
        "SELECT COUNT(*) FROM ("
        "SELECT tenant_id, source_fingerprint FROM lead "
        "WHERE source = 'bot' AND source_fingerprint IS NOT NULL "
        "GROUP BY tenant_id, source_fingerprint HAVING COUNT(*) > 1"
        ") AS duplicates",
    ),
    (
        "duplicate_tenant_order_fingerprint",
        "SELECT COUNT(*) FROM ("
        'SELECT tenant_id, source_fingerprint FROM "order" '
        "WHERE source_fingerprint IS NOT NULL "
        "GROUP BY tenant_id, source_fingerprint HAVING COUNT(*) > 1"
        ") AS duplicates",
    ),
    (
        "duplicate_tenant_requisites_message",
        "SELECT COUNT(*) FROM ("
        "SELECT tenant_id, source, telegram_user_id, telegram_chat_id, "
        "telegram_message_id FROM customer_requisites_recognition "
        "WHERE source IN ('telegram', 'telegram_text') "
        "AND telegram_user_id IS NOT NULL "
        "AND telegram_chat_id IS NOT NULL "
        "AND telegram_message_id IS NOT NULL "
        "GROUP BY tenant_id, source, telegram_user_id, telegram_chat_id, "
        "telegram_message_id HAVING COUNT(*) > 1"
        ") AS duplicates",
    ),
)


DOWNGRADE_PREFLIGHTS: tuple[tuple[str, str], ...] = (
    (
        "cross_tenant_lead_fingerprint",
        "SELECT COUNT(*) FROM ("
        "SELECT source_fingerprint FROM lead "
        "WHERE source = 'bot' AND source_fingerprint IS NOT NULL "
        "GROUP BY source_fingerprint HAVING COUNT(*) > 1"
        ") AS duplicates",
    ),
    (
        "cross_tenant_order_fingerprint",
        "SELECT COUNT(*) FROM ("
        'SELECT source_fingerprint FROM "order" '
        "WHERE source_fingerprint IS NOT NULL "
        "GROUP BY source_fingerprint HAVING COUNT(*) > 1"
        ") AS duplicates",
    ),
    (
        "cross_tenant_requisites_message",
        "SELECT COUNT(*) FROM ("
        "SELECT source, telegram_user_id, telegram_chat_id, telegram_message_id "
        "FROM customer_requisites_recognition "
        "WHERE source IN ('telegram', 'telegram_text') "
        "AND telegram_user_id IS NOT NULL "
        "AND telegram_chat_id IS NOT NULL "
        "AND telegram_message_id IS NOT NULL "
        "GROUP BY source, telegram_user_id, telegram_chat_id, "
        "telegram_message_id HAVING COUNT(*) > 1"
        ") AS duplicates",
    ),
)


def _assert_zero_counts(
    checks: Sequence[tuple[str, str]],
    *,
    action: str,
) -> None:
    connection = op.get_bind()
    failures = []
    for label, query in checks:
        count = int(connection.execute(sa.text(query)).scalar_one() or 0)
        if count:
            failures.append(f"{label}={count}")
    if failures:
        raise RuntimeError(
            f"Refusing tenant provenance {action}: " + "; ".join(failures)
        )


def _foreign_key_name(
    table_name: str,
    constrained_columns: Sequence[str],
    referred_table: str,
) -> str:
    expected_columns = tuple(constrained_columns)
    matches = [
        foreign_key
        for foreign_key in sa.inspect(op.get_bind()).get_foreign_keys(table_name)
        if tuple(foreign_key.get("constrained_columns") or ()) == expected_columns
        and foreign_key.get("referred_table") == referred_table
    ]
    if len(matches) != 1 or not matches[0].get("name"):
        raise RuntimeError(
            "Cannot identify the existing foreign key for "
            f"{table_name}({', '.join(expected_columns)})"
        )
    return str(matches[0]["name"])


def _drop_legacy_foreign_keys() -> None:
    foreign_keys = {
        "lead_storefront": _foreign_key_name(
            "lead", ("storefront_id",), "storefront"
        ),
        "lead_converted_order": _foreign_key_name(
            "lead", ("converted_order_id",), "order"
        ),
        "order_storefront": _foreign_key_name(
            "order", ("storefront_id",), "storefront"
        ),
        "order_customer": _foreign_key_name(
            "order", ("customer_id",), "customer"
        ),
        "requisites_duplicate_customer": _foreign_key_name(
            "customer_requisites_recognition",
            ("duplicate_customer_id",),
            "customer",
        ),
        "requisites_confirmed_customer": _foreign_key_name(
            "customer_requisites_recognition",
            ("confirmed_customer_id",),
            "customer",
        ),
    }

    with op.batch_alter_table("lead") as batch_op:
        batch_op.drop_constraint(
            foreign_keys["lead_storefront"], type_="foreignkey"
        )
        batch_op.drop_constraint(
            foreign_keys["lead_converted_order"], type_="foreignkey"
        )
    with op.batch_alter_table("order") as batch_op:
        batch_op.drop_constraint(
            foreign_keys["order_storefront"], type_="foreignkey"
        )
        batch_op.drop_constraint(
            foreign_keys["order_customer"], type_="foreignkey"
        )
    with op.batch_alter_table(
        "customer_requisites_recognition"
    ) as batch_op:
        batch_op.drop_constraint(
            foreign_keys["requisites_duplicate_customer"],
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            foreign_keys["requisites_confirmed_customer"],
            type_="foreignkey",
        )


def upgrade() -> None:
    _assert_zero_counts(CONTRACT_PREFLIGHTS, action="contract migration")

    op.drop_index(LEAD_FINGERPRINT_INDEX, table_name="lead")
    op.drop_index(ORDER_FINGERPRINT_INDEX, table_name="order")
    op.drop_index(
        REQUISITES_TELEGRAM_INDEX,
        table_name="customer_requisites_recognition",
    )

    with op.batch_alter_table("storefront") as batch_op:
        batch_op.create_unique_constraint(
            STOREFRONT_SCOPE_UNIQUE,
            ["id", "tenant_id"],
        )
    with op.batch_alter_table("customer") as batch_op:
        batch_op.alter_column(
            "tenant_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.create_unique_constraint(
            CUSTOMER_SCOPE_UNIQUE,
            ["id", "tenant_id"],
        )
    with op.batch_alter_table("order") as batch_op:
        batch_op.create_unique_constraint(
            ORDER_SCOPE_UNIQUE,
            ["id", "tenant_id", "storefront_id"],
        )

    _drop_legacy_foreign_keys()

    with op.batch_alter_table("order") as batch_op:
        batch_op.alter_column(
            "tenant_id", existing_type=sa.Integer(), nullable=False
        )
        batch_op.alter_column(
            "storefront_id", existing_type=sa.Integer(), nullable=False
        )
        batch_op.create_foreign_key(
            ORDER_STOREFRONT_SCOPE_FK,
            "storefront",
            ["storefront_id", "tenant_id"],
            ["id", "tenant_id"],
        )
        batch_op.create_foreign_key(
            ORDER_CUSTOMER_SCOPE_FK,
            "customer",
            ["customer_id", "tenant_id"],
            ["id", "tenant_id"],
        )
    with op.batch_alter_table("lead") as batch_op:
        batch_op.alter_column(
            "tenant_id", existing_type=sa.Integer(), nullable=False
        )
        batch_op.alter_column(
            "storefront_id", existing_type=sa.Integer(), nullable=False
        )
        batch_op.create_foreign_key(
            LEAD_STOREFRONT_SCOPE_FK,
            "storefront",
            ["storefront_id", "tenant_id"],
            ["id", "tenant_id"],
        )
        batch_op.create_foreign_key(
            LEAD_CONVERTED_ORDER_SCOPE_FK,
            "order",
            ["converted_order_id", "tenant_id", "storefront_id"],
            ["id", "tenant_id", "storefront_id"],
        )
    with op.batch_alter_table(
        "customer_requisites_recognition"
    ) as batch_op:
        batch_op.alter_column(
            "tenant_id", existing_type=sa.Integer(), nullable=False
        )
        batch_op.create_foreign_key(
            REQUISITES_DUPLICATE_CUSTOMER_SCOPE_FK,
            "customer",
            ["duplicate_customer_id", "tenant_id"],
            ["id", "tenant_id"],
        )
        batch_op.create_foreign_key(
            REQUISITES_CONFIRMED_CUSTOMER_SCOPE_FK,
            "customer",
            ["confirmed_customer_id", "tenant_id"],
            ["id", "tenant_id"],
        )

    op.create_index(
        LEAD_FINGERPRINT_INDEX,
        "lead",
        ["tenant_id", "source_fingerprint"],
        unique=True,
        postgresql_where=sa.text(
            "source = 'bot' AND source_fingerprint IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "source = 'bot' AND source_fingerprint IS NOT NULL"
        ),
    )
    op.create_index(
        ORDER_FINGERPRINT_INDEX,
        "order",
        ["tenant_id", "source_fingerprint"],
        unique=True,
        postgresql_where=sa.text("source_fingerprint IS NOT NULL"),
        sqlite_where=sa.text("source_fingerprint IS NOT NULL"),
    )
    op.create_index(
        REQUISITES_TELEGRAM_INDEX,
        "customer_requisites_recognition",
        [
            "tenant_id",
            "source",
            "telegram_user_id",
            "telegram_chat_id",
            "telegram_message_id",
        ],
        unique=True,
        postgresql_where=sa.text(
            "source IN ('telegram', 'telegram_text') "
            "AND telegram_user_id IS NOT NULL "
            "AND telegram_chat_id IS NOT NULL "
            "AND telegram_message_id IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "source IN ('telegram', 'telegram_text') "
            "AND telegram_user_id IS NOT NULL "
            "AND telegram_chat_id IS NOT NULL "
            "AND telegram_message_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    _assert_zero_counts(DOWNGRADE_PREFLIGHTS, action="contract downgrade")

    op.drop_index(LEAD_FINGERPRINT_INDEX, table_name="lead")
    op.drop_index(ORDER_FINGERPRINT_INDEX, table_name="order")
    op.drop_index(
        REQUISITES_TELEGRAM_INDEX,
        table_name="customer_requisites_recognition",
    )

    with op.batch_alter_table("lead") as batch_op:
        batch_op.drop_constraint(
            LEAD_CONVERTED_ORDER_SCOPE_FK, type_="foreignkey"
        )
        batch_op.drop_constraint(
            LEAD_STOREFRONT_SCOPE_FK, type_="foreignkey"
        )
        batch_op.create_foreign_key(
            "fk_lead_converted_order_id_order",
            "order",
            ["converted_order_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_lead_storefront_id_storefront",
            "storefront",
            ["storefront_id"],
            ["id"],
        )
        batch_op.alter_column(
            "tenant_id", existing_type=sa.Integer(), nullable=True
        )
        batch_op.alter_column(
            "storefront_id", existing_type=sa.Integer(), nullable=True
        )
    with op.batch_alter_table("order") as batch_op:
        batch_op.drop_constraint(
            ORDER_CUSTOMER_SCOPE_FK, type_="foreignkey"
        )
        batch_op.drop_constraint(
            ORDER_STOREFRONT_SCOPE_FK, type_="foreignkey"
        )
        batch_op.create_foreign_key(
            "fk_order_customer_id_customer",
            "customer",
            ["customer_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_order_storefront_id_storefront",
            "storefront",
            ["storefront_id"],
            ["id"],
        )
        batch_op.alter_column(
            "tenant_id", existing_type=sa.Integer(), nullable=True
        )
        batch_op.alter_column(
            "storefront_id", existing_type=sa.Integer(), nullable=True
        )
    with op.batch_alter_table(
        "customer_requisites_recognition"
    ) as batch_op:
        batch_op.drop_constraint(
            REQUISITES_CONFIRMED_CUSTOMER_SCOPE_FK,
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            REQUISITES_DUPLICATE_CUSTOMER_SCOPE_FK,
            type_="foreignkey",
        )
        batch_op.create_foreign_key(
            "fk_customer_requisites_confirmed_customer_id",
            "customer",
            ["confirmed_customer_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_customer_requisites_duplicate_customer_id",
            "customer",
            ["duplicate_customer_id"],
            ["id"],
        )
        batch_op.alter_column(
            "tenant_id", existing_type=sa.Integer(), nullable=True
        )

    with op.batch_alter_table("order") as batch_op:
        batch_op.drop_constraint(ORDER_SCOPE_UNIQUE, type_="unique")
    with op.batch_alter_table("customer") as batch_op:
        batch_op.drop_constraint(CUSTOMER_SCOPE_UNIQUE, type_="unique")
        batch_op.alter_column(
            "tenant_id", existing_type=sa.Integer(), nullable=True
        )
    with op.batch_alter_table("storefront") as batch_op:
        batch_op.drop_constraint(STOREFRONT_SCOPE_UNIQUE, type_="unique")

    op.create_index(
        LEAD_FINGERPRINT_INDEX,
        "lead",
        ["source_fingerprint"],
        unique=True,
        postgresql_where=sa.text(
            "source = 'bot' AND source_fingerprint IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "source = 'bot' AND source_fingerprint IS NOT NULL"
        ),
    )
    op.create_index(
        ORDER_FINGERPRINT_INDEX,
        "order",
        ["source_fingerprint"],
        unique=True,
        postgresql_where=sa.text("source_fingerprint IS NOT NULL"),
        sqlite_where=sa.text("source_fingerprint IS NOT NULL"),
    )
    op.create_index(
        REQUISITES_TELEGRAM_INDEX,
        "customer_requisites_recognition",
        [
            "source",
            "telegram_user_id",
            "telegram_chat_id",
            "telegram_message_id",
        ],
        unique=True,
        postgresql_where=sa.text(
            "source IN ('telegram', 'telegram_text') "
            "AND telegram_user_id IS NOT NULL "
            "AND telegram_chat_id IS NOT NULL "
            "AND telegram_message_id IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "source IN ('telegram', 'telegram_text') "
            "AND telegram_user_id IS NOT NULL "
            "AND telegram_chat_id IS NOT NULL "
            "AND telegram_message_id IS NOT NULL"
        ),
    )
