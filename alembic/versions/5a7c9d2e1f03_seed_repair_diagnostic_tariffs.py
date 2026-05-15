"""seed repair diagnostic tariffs

Revision ID: 5a7c9d2e1f03
Revises: 4d6e8f0a2b31
Create Date: 2026-05-14 08:45:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "5a7c9d2e1f03"
down_revision: Union[str, Sequence[str], None] = "4d6e8f0a2b31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


REPAIR_DIAGNOSTIC_TARIFFS = [
    {
        "selector_label": "Диагностика кондиционера на объекте",
        "estimate_template": "Диагностика кондиционера на объекте",
        "category": "diagnostics",
        "power_range": "на объекте",
        "base_price": 80,
        "sort_order": 100,
        "comment": "Стартовый тариф для тестирования repair workflow; цену можно уточнить.",
    },
    {
        "selector_label": "Диагностика кондиционера в стационаре",
        "estimate_template": "Диагностика кондиционера в стационаре",
        "category": "diagnostics",
        "power_range": "стационар",
        "base_price": 120,
        "sort_order": 110,
        "comment": "Стартовый тариф для тестирования repair workflow; цену можно уточнить.",
    },
]


def upgrade() -> None:
    bind = op.get_bind()
    for tariff in REPAIR_DIAGNOSTIC_TARIFFS:
        existing_id = bind.execute(
            sa.text(
                """
                SELECT id
                FROM service_tariff
                WHERE service_kind = 'repair'
                  AND selector_label = :selector_label
                LIMIT 1
                """
            ),
            {"selector_label": tariff["selector_label"]},
        ).scalar_one_or_none()
        if existing_id is not None:
            continue

        bind.execute(
            sa.text(
                """
                INSERT INTO service_tariff (
                    service_kind, selector_label, estimate_template, category, power_range,
                    base_price, included_route_meters, is_active, sort_order, comment
                ) VALUES (
                    'repair', :selector_label, :estimate_template, :category, :power_range,
                    :base_price, 0, true, :sort_order, :comment
                )
                """
            ),
            tariff,
        )


def downgrade() -> None:
    bind = op.get_bind()
    for tariff in REPAIR_DIAGNOSTIC_TARIFFS:
        bind.execute(
            sa.text(
                """
                DELETE FROM service_tariff
                WHERE service_kind = 'repair'
                  AND selector_label = :selector_label
                  AND category = 'diagnostics'
                  AND comment = :comment
                """
            ),
            {
                "selector_label": tariff["selector_label"],
                "comment": tariff["comment"],
            },
        )
