"""seed pre-install communication route tariff

Revision ID: 8c4d2b6f1a90
Revises: 2d6c4b8e9f31
Create Date: 2026-06-04 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "8c4d2b6f1a90"
down_revision: Union[str, Sequence[str], None] = "2d6c4b8e9f31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PRE_INSTALL_TARIFF = {
    "service_kind": "pre_install",
    "selector_label": "Закладка коммуникаций под кондиционер до 3 м",
    "estimate_template": "Закладка межблочной трассы под кондиционер, включая материалы до 3 м",
    "category": "Wall",
    "power_range": "07-12",
    "base_price": 500,
    "included_route_meters": 3.0,
    "sort_order": 100,
    "comment": (
        "Дополнительная трасса сверх 3 м — 50 BYN/м. Штробление оплачивается отдельно. "
        "При последующей покупке кондиционера у нас финальное довешивание выполняется без доплаты."
    ),
}

PRE_INSTALL_ROUTE_RULE = {
    "rule_type": "per_meter_over_included",
    "name": "Дополнительная трасса сверх 3 м",
    "line_template": "дополнительная трасса {qty} м",
    "unit": "м",
    "unit_price": 50.0,
    "sort_order": 10,
}


def upgrade() -> None:
    bind = op.get_bind()
    tariff_id = bind.execute(
        sa.text(
            """
            SELECT id
            FROM service_tariff
            WHERE service_kind = :service_kind
              AND selector_label = :selector_label
            LIMIT 1
            """
        ),
        {
            "service_kind": PRE_INSTALL_TARIFF["service_kind"],
            "selector_label": PRE_INSTALL_TARIFF["selector_label"],
        },
    ).scalar_one_or_none()

    if tariff_id is None:
        tariff_id = bind.execute(
            sa.text(
                """
                INSERT INTO service_tariff (
                    service_kind, selector_label, estimate_template, category, power_range,
                    base_price, included_route_meters, is_active, sort_order, comment
                ) VALUES (
                    :service_kind, :selector_label, :estimate_template, :category, :power_range,
                    :base_price, :included_route_meters, true, :sort_order, :comment
                )
                RETURNING id
                """
            ),
            PRE_INSTALL_TARIFF,
        ).scalar_one()

    existing_rule_id = bind.execute(
        sa.text(
            """
            SELECT id
            FROM service_tariff_rule
            WHERE tariff_id = :tariff_id
              AND rule_type = :rule_type
              AND name = :name
            LIMIT 1
            """
        ),
        {
            "tariff_id": int(tariff_id),
            "rule_type": PRE_INSTALL_ROUTE_RULE["rule_type"],
            "name": PRE_INSTALL_ROUTE_RULE["name"],
        },
    ).scalar_one_or_none()

    if existing_rule_id is not None:
        return

    bind.execute(
        sa.text(
            """
            INSERT INTO service_tariff_rule (
                tariff_id, rule_type, name, line_template, unit, unit_price,
                is_optional, is_favorite, is_active, sort_order, service_id
            ) VALUES (
                :tariff_id, :rule_type, :name, :line_template, :unit, :unit_price,
                false, false, true, :sort_order, NULL
            )
            """
        ),
        {"tariff_id": int(tariff_id), **PRE_INSTALL_ROUTE_RULE},
    )


def downgrade() -> None:
    bind = op.get_bind()
    tariff_id = bind.execute(
        sa.text(
            """
            SELECT id
            FROM service_tariff
            WHERE service_kind = :service_kind
              AND selector_label = :selector_label
              AND estimate_template = :estimate_template
              AND category = :category
              AND power_range = :power_range
              AND base_price = :base_price
              AND included_route_meters = :included_route_meters
              AND comment = :comment
            LIMIT 1
            """
        ),
        PRE_INSTALL_TARIFF,
    ).scalar_one_or_none()
    if tariff_id is None:
        return

    bind.execute(
        sa.text(
            """
            DELETE FROM service_tariff_rule
            WHERE tariff_id = :tariff_id
              AND rule_type = :rule_type
              AND name = :name
              AND line_template = :line_template
              AND unit = :unit
              AND unit_price = :unit_price
            """
        ),
        {"tariff_id": int(tariff_id), **PRE_INSTALL_ROUTE_RULE},
    )
    bind.execute(
        sa.text("DELETE FROM service_tariff WHERE id = :tariff_id"),
        {"tariff_id": int(tariff_id)},
    )
