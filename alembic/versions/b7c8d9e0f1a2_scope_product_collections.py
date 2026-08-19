"""scope product collections to exact tenant storefront

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "b7c8d9e0f1a2"
down_revision: str | None = "a6b7c8d9e0f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _canonical_scope() -> tuple[int, int]:
    rows = op.get_bind().execute(
        sa.text(
            "SELECT tenant.id, storefront.id "
            "FROM tenant JOIN storefront ON storefront.tenant_id = tenant.id "
            "WHERE tenant.is_system IS TRUE AND storefront.is_default IS TRUE"
        )
    ).all()
    if len(rows) != 1:
        raise RuntimeError(
            "ProductCollection backfill requires exactly one system tenant/default storefront"
        )
    return int(rows[0][0]), int(rows[0][1])


def _drop_fk_for_columns(table: str, columns: list[str]) -> None:
    expected = set(columns)
    foreign_keys = sa.inspect(op.get_bind()).get_foreign_keys(table)
    names = [
        item.get("name")
        for item in foreign_keys
        if set(item.get("constrained_columns") or ()) == expected
    ]
    if len(names) != 1 or not names[0]:
        raise RuntimeError(
            f"Expected exactly one foreign key on {table}({', '.join(columns)})"
        )
    op.drop_constraint(str(names[0]), table, type_="foreignkey")


def upgrade() -> None:
    tenant_id, storefront_id = _canonical_scope()

    for table in (
        "product_collection",
        "product_collection_item",
        "product_collection_placement",
    ):
        op.add_column(table, sa.Column("tenant_id", sa.Integer(), nullable=True))
        op.add_column(table, sa.Column("storefront_id", sa.Integer(), nullable=True))

    op.execute(
        sa.text(
            "UPDATE product_collection SET tenant_id = :tenant_id, storefront_id = :storefront_id"
        ).bindparams(tenant_id=tenant_id, storefront_id=storefront_id)
    )
    for table in ("product_collection_item", "product_collection_placement"):
        op.execute(
            sa.text(
                f"UPDATE {table} AS child "
                "SET tenant_id = parent.tenant_id, storefront_id = parent.storefront_id "
                "FROM product_collection AS parent "
                "WHERE parent.id = child.collection_id"
            )
        )
        missing = int(
            op.get_bind()
            .execute(
                sa.text(
                    f"SELECT COUNT(*) FROM {table} "
                    "WHERE tenant_id IS NULL OR storefront_id IS NULL"
                )
            )
            .scalar_one()
        )
        if missing:
            raise RuntimeError(f"Cannot scope {missing} orphan rows in {table}")

    # Preserve rolling-deploy compatibility with the previous image. Legacy
    # inserts do not know the new columns: parent rows fail closed to the one
    # canonical system/default scope, while children inherit the exact parent.
    op.execute(
        """
        CREATE FUNCTION product_collection_fill_scope() RETURNS trigger AS $$
        DECLARE
            canonical_tenant_id integer;
            canonical_storefront_id integer;
            candidate_count integer;
        BEGIN
            IF NEW.tenant_id IS NULL AND NEW.storefront_id IS NULL THEN
                SELECT COUNT(*), MIN(tenant.id), MIN(storefront.id)
                INTO candidate_count, canonical_tenant_id, canonical_storefront_id
                FROM tenant
                JOIN storefront ON storefront.tenant_id = tenant.id
                WHERE tenant.is_system IS TRUE AND storefront.is_default IS TRUE;
                IF candidate_count != 1 THEN
                    RAISE EXCEPTION 'Canonical ProductCollection scope is unavailable';
                END IF;
                NEW.tenant_id := canonical_tenant_id;
                NEW.storefront_id := canonical_storefront_id;
            ELSIF NEW.tenant_id IS NULL OR NEW.storefront_id IS NULL THEN
                RAISE EXCEPTION 'Partial ProductCollection scope is forbidden';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE FUNCTION product_collection_child_fill_scope() RETURNS trigger AS $$
        DECLARE
            parent_tenant_id integer;
            parent_storefront_id integer;
        BEGIN
            IF NEW.tenant_id IS NULL AND NEW.storefront_id IS NULL THEN
                SELECT tenant_id, storefront_id
                INTO parent_tenant_id, parent_storefront_id
                FROM product_collection
                WHERE id = NEW.collection_id;
                IF NOT FOUND THEN
                    RAISE EXCEPTION 'ProductCollection parent is unavailable';
                END IF;
                NEW.tenant_id := parent_tenant_id;
                NEW.storefront_id := parent_storefront_id;
            ELSIF NEW.tenant_id IS NULL OR NEW.storefront_id IS NULL THEN
                RAISE EXCEPTION 'Partial ProductCollection child scope is forbidden';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_product_collection_fill_scope "
        "BEFORE INSERT ON product_collection FOR EACH ROW "
        "EXECUTE FUNCTION product_collection_fill_scope()"
    )
    for table in ("product_collection_item", "product_collection_placement"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_fill_scope "
            f"BEFORE INSERT ON {table} FOR EACH ROW "
            "EXECUTE FUNCTION product_collection_child_fill_scope()"
        )

    for table in (
        "product_collection",
        "product_collection_item",
        "product_collection_placement",
    ):
        op.alter_column(table, "tenant_id", nullable=False)
        op.alter_column(table, "storefront_id", nullable=False)
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"], unique=False)
        op.create_index(
            f"ix_{table}_storefront_id",
            table,
            ["storefront_id"],
            unique=False,
        )
        op.create_foreign_key(
            f"fk_{table}_tenant",
            table,
            "tenant",
            ["tenant_id"],
            ["id"],
        )
        op.create_foreign_key(
            f"fk_{table}_storefront_tenant",
            table,
            "storefront",
            ["storefront_id", "tenant_id"],
            ["id", "tenant_id"],
        )

    _drop_fk_for_columns("product_collection", ["fallback_collection_id"])
    _drop_fk_for_columns("product_collection_item", ["collection_id"])
    _drop_fk_for_columns("product_collection_placement", ["collection_id"])

    op.drop_constraint("uq_product_collection_slug", "product_collection", type_="unique")
    op.drop_constraint(
        "uq_product_collection_item_product",
        "product_collection_item",
        type_="unique",
    )
    op.drop_constraint(
        "uq_product_collection_item_position",
        "product_collection_item",
        type_="unique",
    )
    op.drop_constraint(
        "uq_product_collection_placement_slot",
        "product_collection_placement",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_product_collection_id_scope",
        "product_collection",
        ["id", "tenant_id", "storefront_id"],
    )
    op.create_unique_constraint(
        "uq_product_collection_scope_slug",
        "product_collection",
        ["tenant_id", "storefront_id", "slug"],
    )
    op.create_foreign_key(
        "fk_product_collection_fallback_scope",
        "product_collection",
        "product_collection",
        ["fallback_collection_id", "tenant_id", "storefront_id"],
        ["id", "tenant_id", "storefront_id"],
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_foreign_key(
        "fk_product_collection_fallback_delete",
        "product_collection",
        "product_collection",
        ["fallback_collection_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_product_collection_item_collection_scope",
        "product_collection_item",
        "product_collection",
        ["collection_id", "tenant_id", "storefront_id"],
        ["id", "tenant_id", "storefront_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_product_collection_placement_collection_scope",
        "product_collection_placement",
        "product_collection",
        ["collection_id", "tenant_id", "storefront_id"],
        ["id", "tenant_id", "storefront_id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_product_collection_item_scope_product",
        "product_collection_item",
        ["tenant_id", "storefront_id", "collection_id", "product_id"],
    )
    op.create_unique_constraint(
        "uq_product_collection_item_scope_position",
        "product_collection_item",
        ["tenant_id", "storefront_id", "collection_id", "position"],
    )
    op.create_unique_constraint(
        "uq_product_collection_placement_scope_slot",
        "product_collection_placement",
        [
            "tenant_id",
            "storefront_id",
            "surface_key",
            "slot_key",
            "collection_id",
        ],
    )


def downgrade() -> None:
    tenant_id, storefront_id = _canonical_scope()
    foreign_scope_rows = int(
        op.get_bind()
        .execute(
            sa.text(
                "SELECT COUNT(*) FROM product_collection "
                "WHERE tenant_id != :tenant_id OR storefront_id != :storefront_id"
            ).bindparams(tenant_id=tenant_id, storefront_id=storefront_id)
        )
        .scalar_one()
    )
    if foreign_scope_rows:
        raise RuntimeError(
            "Refusing to downgrade scoped ProductCollections while non-canonical rows exist"
        )

    op.execute(
        "DROP TRIGGER trg_product_collection_placement_fill_scope "
        "ON product_collection_placement"
    )
    op.execute(
        "DROP TRIGGER trg_product_collection_item_fill_scope "
        "ON product_collection_item"
    )
    op.execute(
        "DROP TRIGGER trg_product_collection_fill_scope ON product_collection"
    )
    op.execute("DROP FUNCTION product_collection_child_fill_scope()")
    op.execute("DROP FUNCTION product_collection_fill_scope()")

    op.drop_constraint(
        "fk_product_collection_fallback_delete",
        "product_collection",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_product_collection_fallback_scope",
        "product_collection",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_product_collection_item_collection_scope",
        "product_collection_item",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_product_collection_placement_collection_scope",
        "product_collection_placement",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_product_collection_item_scope_product",
        "product_collection_item",
        type_="unique",
    )
    op.drop_constraint(
        "uq_product_collection_item_scope_position",
        "product_collection_item",
        type_="unique",
    )
    op.drop_constraint(
        "uq_product_collection_placement_scope_slot",
        "product_collection_placement",
        type_="unique",
    )
    op.drop_constraint(
        "uq_product_collection_scope_slug",
        "product_collection",
        type_="unique",
    )
    op.drop_constraint(
        "uq_product_collection_id_scope",
        "product_collection",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_product_collection_slug", "product_collection", ["slug"]
    )
    op.create_unique_constraint(
        "uq_product_collection_item_product",
        "product_collection_item",
        ["collection_id", "product_id"],
    )
    op.create_unique_constraint(
        "uq_product_collection_item_position",
        "product_collection_item",
        ["collection_id", "position"],
    )
    op.create_unique_constraint(
        "uq_product_collection_placement_slot",
        "product_collection_placement",
        ["surface_key", "slot_key", "collection_id"],
    )
    op.create_foreign_key(
        "product_collection_fallback_collection_id_fkey",
        "product_collection",
        "product_collection",
        ["fallback_collection_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "product_collection_item_collection_id_fkey",
        "product_collection_item",
        "product_collection",
        ["collection_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "product_collection_placement_collection_id_fkey",
        "product_collection_placement",
        "product_collection",
        ["collection_id"],
        ["id"],
        ondelete="CASCADE",
    )

    for table in (
        "product_collection_placement",
        "product_collection_item",
        "product_collection",
    ):
        op.drop_constraint(f"fk_{table}_storefront_tenant", table, type_="foreignkey")
        op.drop_constraint(f"fk_{table}_tenant", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_storefront_id", table_name=table)
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        op.drop_column(table, "storefront_id")
        op.drop_column(table, "tenant_id")
