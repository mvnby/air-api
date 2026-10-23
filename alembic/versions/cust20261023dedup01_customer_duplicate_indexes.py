"""Index tenant-scoped duplicate candidates without changing customer data.

Build concurrently; interrupted builds can be retried safely. No backfill.
"""

from alembic import op
import sqlalchemy as sa

revision = "cust20261023dedup01"
down_revision = "dash20261023snap01"
branch_labels = None
depends_on = None

# Frozen expressions: migrations must not depend on future normalizer changes.
PHONE_KEY = "(CASE WHEN (regexp_replace(phone, '[^0-9]', '', 'g') LIKE '375%' AND length(regexp_replace(phone, '[^0-9]', '', 'g')) >= 12) THEN substr(regexp_replace(phone, '[^0-9]', '', 'g'), 1, 12) WHEN (regexp_replace(phone, '[^0-9]', '', 'g') LIKE '80%' AND length(regexp_replace(phone, '[^0-9]', '', 'g')) >= 11) THEN '375' || substr(regexp_replace(phone, '[^0-9]', '', 'g'), 3, 9) WHEN (regexp_replace(phone, '[^0-9]', '', 'g') LIKE '0%' AND length(regexp_replace(phone, '[^0-9]', '', 'g')) >= 10) THEN '375' || substr(regexp_replace(phone, '[^0-9]', '', 'g'), 2, 9) WHEN (length(regexp_replace(phone, '[^0-9]', '', 'g')) = 9) THEN '375' || regexp_replace(phone, '[^0-9]', '', 'g') ELSE regexp_replace(phone, '[^0-9]', '', 'g') END)"
EMAIL_KEY = "lower(translate(btrim(email, '\t\n\x0b\x0c\r\x1c\x1d\x1e\x1f \x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000'), 'K', 'K') COLLATE \"C\")"
INN_KEY = "btrim(inn, '\t\n\x0b\x0c\r\x1c\x1d\x1e\x1f \x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000')"
NON_ASCII_PATTERN = "[^\\u0001-\\u007f]"


def _index_specs():
    for field, expression in (
        ("phone", PHONE_KEY),
        ("email", EMAIL_KEY),
        ("inn", INN_KEY),
    ):
        yield f"ix_customer_duplicate_{field}", ["tenant_id", sa.text(expression)], None
    for field in ("phone", "email"):
        yield (
            f"ix_customer_duplicate_{field}_unicode",
            ["tenant_id"],
            sa.text(f"{field} ~ '{NON_ASCII_PATTERN}'"),
        )


def upgrade():
    # CONCURRENTLY avoids blocking customer writes while scanning existing rows.
    with op.get_context().autocommit_block():
        for name, columns, predicate in _index_specs():
            valid = (
                op.get_bind()
                .execute(
                    sa.text(
                        "SELECT indisvalid FROM pg_index WHERE indexrelid = to_regclass(:name)"
                    ),
                    {"name": name},
                )
                .scalar_one_or_none()
            )
            if valid:
                continue
            if valid is False:
                op.drop_index(name, table_name="customer", postgresql_concurrently=True)
            options = {"postgresql_where": predicate} if predicate is not None else {}
            op.create_index(
                name, "customer", columns, postgresql_concurrently=True, **options
            )


def downgrade():
    with op.get_context().autocommit_block():
        for name, _, _ in reversed(list(_index_specs())):
            op.drop_index(
                name,
                table_name="customer",
                if_exists=True,
                postgresql_concurrently=True,
            )
