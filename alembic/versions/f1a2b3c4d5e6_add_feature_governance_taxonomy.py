"""add feature governance taxonomy

Revision ID: f1a2b3c4d5e6
Revises: e46f8a1c2d30
Create Date: 2026-07-22 12:00:00
"""

from typing import Sequence, Union

from alembic import op


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e46f8a1c2d30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO feature_category (slug, name, sort_order, is_active, created_at, updated_at)
        VALUES ('heating', 'Обогрев', 60, true, now(), now())
        ON CONFLICT (slug) DO UPDATE
        SET name = EXCLUDED.name,
            sort_order = EXCLUDED.sort_order,
            is_active = true,
            updated_at = now()
        """
    )
    category_updates = (
        ("comfort", "Комфорт", 10),
        ("air-quality", "Воздух и очистка", 20),
        ("control", "Управление", 30),
        ("efficiency", "Энергоэффективность", 40),
        ("performance", "Производительность", 50),
        ("design", "Дизайн", 70),
        ("reliability", "Надёжность", 80),
        ("installation", "Монтаж и совместимость", 90),
    )
    for slug, name, sort_order in category_updates:
        op.execute(
            f"""
            UPDATE feature_category
            SET name = '{name}', sort_order = {sort_order}, updated_at = now()
            WHERE slug = '{slug}'
            """
        )
    op.execute(
        """
        UPDATE feature
        SET category_id = (SELECT id FROM feature_category WHERE slug = 'heating'),
            updated_at = now()
        WHERE slug IN ('heating-minus-20', 'heating-minus-25')
        """
    )
    op.execute(
        """
        UPDATE feature
        SET scope_type = CASE
                WHEN slug IN ('vstroennyi-wi-fi', 'wifi-ready') THEN 'derived'
                ELSE 'universal'
            END,
            brand_id = NULL,
            updated_at = now()
        WHERE slug IN (
            'vstroennyi-wi-fi',
            'wifi-ready',
            'bipoliarnyi-ionizator',
            'uf-sterilizatsiia'
        )
        """
    )
    op.execute(
        """
        DELETE FROM feature_series_link
        WHERE feature_id = (SELECT id FROM feature WHERE slug = 'smart-inverter-tcl')
        """
    )
    op.execute(
        """
        UPDATE feature
        SET is_active = false,
            archived_at = COALESCE(archived_at, now()),
            updated_at = now()
        WHERE slug = 'smart-inverter-tcl'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE feature
        SET is_active = true, archived_at = NULL, updated_at = now()
        WHERE slug = 'smart-inverter-tcl'
        """
    )
    op.execute(
        """
        UPDATE feature
        SET scope_type = CASE
                WHEN slug IN ('vstroennyi-wi-fi', 'wifi-ready') THEN 'derived'
                ELSE 'brand'
            END,
            brand_id = (SELECT id FROM brand WHERE slug = 'tcl'),
            updated_at = now()
        WHERE slug IN (
            'vstroennyi-wi-fi',
            'wifi-ready',
            'bipoliarnyi-ionizator',
            'uf-sterilizatsiia'
        )
        """
    )
    op.execute(
        """
        UPDATE feature
        SET category_id = (SELECT id FROM feature_category WHERE slug = 'performance'),
            updated_at = now()
        WHERE slug IN ('heating-minus-20', 'heating-minus-25')
        """
    )
    op.execute("DELETE FROM feature_category WHERE slug = 'heating'")
    category_updates = (
        ("comfort", "Комфорт", 10),
        ("control", "Управление", 20),
        ("air-quality", "Очистка воздуха", 30),
        ("efficiency", "Энергоэффективность", 40),
        ("performance", "Производительность", 50),
        ("reliability", "Надёжность", 60),
        ("installation", "Монтаж", 70),
        ("design", "Дизайн", 80),
    )
    for slug, name, sort_order in category_updates:
        op.execute(
            f"""
            UPDATE feature_category
            SET name = '{name}', sort_order = {sort_order}, updated_at = now()
            WHERE slug = '{slug}'
            """
        )
