"""Drop the legacy product.area mirror.

Revision ID: c35e9a2b7d41
Revises: b24d8f1a6c30
"""

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "c35e9a2b7d41"
down_revision: Union[str, Sequence[str], None] = "b24d8f1a6c30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


AREA_VALUE_SQL = "jsonb_extract_path_text(CAST(specs AS jsonb), 'area_m2')"


def upgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_sync_product_area_transition ON product")
    op.execute("DROP FUNCTION IF EXISTS sync_product_area_transition()")
    op.drop_index("ix_product_area", table_name="product")
    op.drop_column("product", "area")
    op.create_check_constraint(
        "ck_product_specs_area_m2_positive_number",
        "product",
        """
        CASE
            WHEN CAST(specs AS jsonb) ? 'area_m2' THEN
                CASE
                    WHEN specs ->> 'area_m2' ~ '^[0-9]+([.][0-9]+)?$'
                        THEN CAST(specs ->> 'area_m2' AS numeric) > 0
                    ELSE false
                END
            ELSE true
        END
        """,
    )
    op.execute(
        f"""
        CREATE INDEX ix_product_specs_area_m2
        ON product ((CAST({AREA_VALUE_SQL} AS double precision)))
        """
    )


def downgrade() -> None:
    op.drop_index("ix_product_specs_area_m2", table_name="product")
    op.drop_constraint(
        "ck_product_specs_area_m2_positive_number",
        "product",
        type_="check",
    )
    op.add_column("product", sa.Column("area", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE product
        SET area = CASE
            WHEN specs ->> 'area_m2' ~ '^[0-9]+([.][0-9]+)?$'
                THEN CEIL(CAST(specs ->> 'area_m2' AS numeric))::integer
            ELSE 0
        END
        """
    )
    op.alter_column(
        "product",
        "area",
        nullable=False,
        server_default=sa.text("0"),
    )
    op.create_index("ix_product_area", "product", ["area"], unique=False)
    op.execute(
        """
        CREATE OR REPLACE FUNCTION sync_product_area_transition()
        RETURNS trigger AS $$
        DECLARE
            canonical_text text;
        BEGIN
            NEW.specs := (
                COALESCE(NEW.specs, '{}'::json) :: jsonb - 'recommended_area_m2'
            ) :: json;
            canonical_text := NEW.specs ->> 'area_m2';

            IF canonical_text ~ '^[0-9]+([.,][0-9]+)?$'
               AND (TG_OP = 'INSERT' OR NEW.specs::jsonb IS DISTINCT FROM OLD.specs::jsonb) THEN
                NEW.area := CEIL(REPLACE(canonical_text, ',', '.')::numeric)::integer;
            ELSIF NEW.area > 0 AND (TG_OP = 'INSERT' OR NEW.area IS DISTINCT FROM OLD.area) THEN
                NEW.specs := (
                    COALESCE(NEW.specs, '{}'::json) :: jsonb
                    || jsonb_build_object('area_m2', NEW.area)
                ) :: json;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_sync_product_area_transition
        BEFORE INSERT OR UPDATE OF area, specs ON product
        FOR EACH ROW EXECUTE FUNCTION sync_product_area_transition()
        """
    )
