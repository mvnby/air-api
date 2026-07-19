"""Canonicalize product area in specs.area_m2.

Revision ID: b24d8f1a6c30
Revises: a13c5e7f9b24
"""

from collections.abc import Sequence
from typing import Union

from alembic import op


revision: str = "b24d8f1a6c30"
down_revision: Union[str, Sequence[str], None] = "a13c5e7f9b24"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE product
        SET specs = (
            CASE
                WHEN NULLIF(BTRIM(COALESCE(specs ->> 'area_m2', '')), '') IS NOT NULL
                    THEN (COALESCE(specs, '{}'::json) :: jsonb - 'recommended_area_m2')
                WHEN NULLIF(BTRIM(COALESCE(specs ->> 'recommended_area_m2', '')), '') IS NOT NULL
                    THEN (
                        COALESCE(specs, '{}'::json) :: jsonb
                        - 'recommended_area_m2'
                        || jsonb_build_object('area_m2', specs -> 'recommended_area_m2')
                    )
                WHEN area > 0
                    THEN (
                        COALESCE(specs, '{}'::json) :: jsonb
                        - 'recommended_area_m2'
                        || jsonb_build_object('area_m2', area)
                    )
                ELSE COALESCE(specs, '{}'::json) :: jsonb - 'recommended_area_m2' - 'area_m2'
            END
        ) :: json
        """
    )
    op.execute(
        """
        UPDATE product
        SET area = CEIL(REPLACE(specs ->> 'area_m2', ',', '.')::numeric)::integer
        WHERE COALESCE(specs ->> 'area_m2', '') ~ '^[0-9]+([.,][0-9]+)?$'
        """
    )
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


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_sync_product_area_transition ON product")
    op.execute("DROP FUNCTION IF EXISTS sync_product_area_transition()")
