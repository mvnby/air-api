"""refactor service tariffs to parent/child model

Revision ID: 7d4e1a2b3c9f
Revises: 2b3c4d5e6f70
Create Date: 2026-04-22 11:20:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "7d4e1a2b3c9f"
down_revision: Union[str, Sequence[str], None] = "2b3c4d5e6f70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _build_selector_label(category: str, power_range: str) -> str:
    category_l = (category or "").strip().lower()
    power = (power_range or "").strip()
    if "wall" in category_l:
        base = "Монтаж настенного"
    elif "cassette" in category_l:
        base = "Монтаж кассетного"
    elif "ceiling" in category_l:
        base = "Монтаж потолочного"
    elif "duct" in category_l:
        base = "Монтаж канального"
    else:
        base = f"Монтаж {category.strip()}" if category.strip() else "Монтаж кондиционера"
    if power:
        return f"{base} {power}"
    return base


def _build_estimate_template(category: str, power_range: str) -> str:
    power = (power_range or "").strip()
    if power:
        return f"Монтаж сплит-системы ({category.strip() or 'базовый'}) мощностью {power}, включая расходные материалы"
    return "Монтаж сплит-системы, включая расходные материалы"


def upgrade() -> None:
    op.create_table(
        "service_tariff",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("service_kind", sa.String(), nullable=False, server_default=sa.text("'installation'")),
        sa.Column("selector_label", sa.String(), nullable=False),
        sa.Column("estimate_template", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False, server_default=sa.text("''")),
        sa.Column("power_range", sa.String(), nullable=False, server_default=sa.text("''")),
        sa.Column("base_price", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("included_route_meters", sa.Float(), nullable=False, server_default=sa.text("3.0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("comment", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=True, server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_service_tariff_service_kind", "service_tariff", ["service_kind"], unique=False)
    op.create_index("ix_service_tariff_selector_label", "service_tariff", ["selector_label"], unique=False)
    op.create_index("ix_service_tariff_category", "service_tariff", ["category"], unique=False)
    op.create_index("ix_service_tariff_power_range", "service_tariff", ["power_range"], unique=False)
    op.create_index("ix_service_tariff_is_active", "service_tariff", ["is_active"], unique=False)
    op.create_index("ix_service_tariff_sort_order", "service_tariff", ["sort_order"], unique=False)

    op.create_table(
        "service_tariff_rule",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tariff_id", sa.Integer(), nullable=False),
        sa.Column("rule_type", sa.String(), nullable=False, server_default=sa.text("'per_unit_manual'")),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("line_template", sa.String(), nullable=False, server_default=sa.text("'{name}'")),
        sa.Column("unit", sa.String(), nullable=False, server_default=sa.text("'шт'")),
        sa.Column("unit_price", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("is_optional", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("service_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=True, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["service_id"], ["service.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tariff_id"], ["service_tariff.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_service_tariff_rule_tariff_id", "service_tariff_rule", ["tariff_id"], unique=False)
    op.create_index("ix_service_tariff_rule_rule_type", "service_tariff_rule", ["rule_type"], unique=False)
    op.create_index("ix_service_tariff_rule_name", "service_tariff_rule", ["name"], unique=False)
    op.create_index("ix_service_tariff_rule_is_optional", "service_tariff_rule", ["is_optional"], unique=False)
    op.create_index("ix_service_tariff_rule_is_active", "service_tariff_rule", ["is_active"], unique=False)
    op.create_index("ix_service_tariff_rule_sort_order", "service_tariff_rule", ["sort_order"], unique=False)
    op.create_index("ix_service_tariff_rule_service_id", "service_tariff_rule", ["service_id"], unique=False)

    op.add_column("service_estimate", sa.Column("tariff_id", sa.Integer(), nullable=True))
    op.create_index("ix_service_estimate_tariff_id", "service_estimate", ["tariff_id"], unique=False)
    op.create_foreign_key(
        "fk_service_estimate_tariff_id_service_tariff",
        "service_estimate",
        "service_tariff",
        ["tariff_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("service_estimate_item", sa.Column("service_id", sa.Integer(), nullable=True))
    op.create_index("ix_service_estimate_item_service_id", "service_estimate_item", ["service_id"], unique=False)
    op.create_foreign_key(
        "fk_service_estimate_item_service_id_service",
        "service_estimate_item",
        "service",
        ["service_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute(
        sa.text(
            "UPDATE service_estimate SET service_kind = 'installation' WHERE service_kind = 'install'"
        )
    )

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, category, power_range, base_price, extra_pipe_price, included_pipe_meters, comment
            FROM installation_rates
            ORDER BY id
            """
        )
    ).mappings().all()

    for row in rows:
        selector_label = _build_selector_label(str(row["category"] or ""), str(row["power_range"] or ""))
        estimate_template = _build_estimate_template(str(row["category"] or ""), str(row["power_range"] or ""))
        tariff_id = bind.execute(
            sa.text(
                """
                INSERT INTO service_tariff (
                    service_kind, selector_label, estimate_template, category, power_range,
                    base_price, included_route_meters, is_active, sort_order, comment
                ) VALUES (
                    'installation', :selector_label, :estimate_template, :category, :power_range,
                    :base_price, :included_route_meters, true, :sort_order, :comment
                )
                RETURNING id
                """
            ),
            {
                "selector_label": selector_label,
                "estimate_template": estimate_template,
                "category": str(row["category"] or "").strip(),
                "power_range": str(row["power_range"] or "").strip(),
                "base_price": int(row["base_price"] or 0),
                "included_route_meters": float(row["included_pipe_meters"] or 0),
                "sort_order": int(row["id"] or 0),
                "comment": row["comment"],
            },
        ).scalar_one()

        bind.execute(
            sa.text(
                """
                INSERT INTO service_tariff_rule (
                    tariff_id, rule_type, name, line_template, unit, unit_price,
                    is_optional, is_active, sort_order, service_id
                ) VALUES (
                    :tariff_id, 'per_meter_over_included',
                    'Дополнительная трасса', 'доп. трасса {qty} {unit}',
                    'м', :unit_price, false, true, 10, NULL
                )
                """
            ),
            {
                "tariff_id": int(tariff_id),
                "unit_price": float(row["extra_pipe_price"] or 0),
            },
        )
        bind.execute(
            sa.text(
                """
                INSERT INTO service_tariff_rule (
                    tariff_id, rule_type, name, line_template, unit, unit_price,
                    is_optional, is_active, sort_order, service_id
                ) VALUES (
                    :tariff_id, 'per_hole_manual',
                    'Дополнительные отверстия', '{extra_holes_count} доп. отверстий',
                    'шт', 35, false, true, 20, NULL
                )
                """
            ),
            {"tariff_id": int(tariff_id)},
        )


def downgrade() -> None:
    op.drop_constraint("fk_service_estimate_item_service_id_service", "service_estimate_item", type_="foreignkey")
    op.drop_index("ix_service_estimate_item_service_id", table_name="service_estimate_item")
    op.drop_column("service_estimate_item", "service_id")

    op.drop_constraint("fk_service_estimate_tariff_id_service_tariff", "service_estimate", type_="foreignkey")
    op.drop_index("ix_service_estimate_tariff_id", table_name="service_estimate")
    op.drop_column("service_estimate", "tariff_id")

    op.drop_index("ix_service_tariff_rule_service_id", table_name="service_tariff_rule")
    op.drop_index("ix_service_tariff_rule_sort_order", table_name="service_tariff_rule")
    op.drop_index("ix_service_tariff_rule_is_active", table_name="service_tariff_rule")
    op.drop_index("ix_service_tariff_rule_is_optional", table_name="service_tariff_rule")
    op.drop_index("ix_service_tariff_rule_name", table_name="service_tariff_rule")
    op.drop_index("ix_service_tariff_rule_rule_type", table_name="service_tariff_rule")
    op.drop_index("ix_service_tariff_rule_tariff_id", table_name="service_tariff_rule")
    op.drop_table("service_tariff_rule")

    op.drop_index("ix_service_tariff_sort_order", table_name="service_tariff")
    op.drop_index("ix_service_tariff_is_active", table_name="service_tariff")
    op.drop_index("ix_service_tariff_power_range", table_name="service_tariff")
    op.drop_index("ix_service_tariff_category", table_name="service_tariff")
    op.drop_index("ix_service_tariff_selector_label", table_name="service_tariff")
    op.drop_index("ix_service_tariff_service_kind", table_name="service_tariff")
    op.drop_table("service_tariff")
