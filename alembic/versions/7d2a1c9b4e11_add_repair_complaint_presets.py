"""add repair complaint presets

Revision ID: 7d2a1c9b4e11
Revises: 6b8d1f4c2a90
Create Date: 2026-05-15 09:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "7d2a1c9b4e11"
down_revision: Union[str, Sequence[str], None] = "6b8d1f4c2a90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PRESETS = [
    {
        "complaint_group": "water_drainage",
        "customer_phrase": "Капает вода в комнату",
        "document_wording": "Нарушение герметичности дренажной системы / закупорка дренажного канала.",
        "likely_diagnosis": "Засор дренажного поддона или канала, перегиб дренажной трубки, загрязнение трассы.",
        "is_favorite": True,
        "sort_order": 10,
    },
    {
        "complaint_group": "cooling",
        "customer_phrase": "Вообще не холодит",
        "document_wording": "Отсутствие теплообмена в режиме охлаждения.",
        "likely_diagnosis": "Утечка хладагента, отказ пускового конденсатора, неисправность компрессора или платы управления.",
        "is_favorite": True,
        "sort_order": 20,
    },
    {
        "complaint_group": "smell_contamination",
        "customer_phrase": "Пахнет сыростью или плесенью",
        "document_wording": "Наличие неприятных запахов при работе вентилятора внутреннего блока.",
        "likely_diagnosis": "Бактериальное загрязнение теплообменника, дренажного поддона или фильтров; требуется чистка и дезинфекция.",
        "is_favorite": True,
        "sort_order": 30,
    },
    {
        "complaint_group": "shutdown_error",
        "customer_phrase": "Сам выключается",
        "document_wording": "Аварийная остановка системы с индикацией ошибки либо без устойчивого рабочего режима.",
        "likely_diagnosis": "Срабатывание защиты, перегрев, неисправность датчика, платы управления или недостаток хладагента.",
        "is_favorite": True,
        "sort_order": 40,
    },
    {
        "complaint_group": "noise_vibration",
        "customer_phrase": "Шумит или вибрирует",
        "document_wording": "Повышенный шум и/или вибрация при работе оборудования.",
        "likely_diagnosis": "Загрязнение крыльчатки, износ подшипников, нарушение крепления, деформация корпуса или дисбаланс вентилятора.",
        "is_favorite": False,
        "sort_order": 50,
    },
    {
        "complaint_group": "control_electronics",
        "customer_phrase": "Не реагирует на пульт",
        "document_wording": "Отсутствует управление оборудованием с пульта дистанционного управления.",
        "likely_diagnosis": "Разряд батареек, неисправность пульта, приемника ИК-сигнала или платы управления.",
        "is_favorite": False,
        "sort_order": 60,
    },
    {
        "complaint_group": "freezing",
        "customer_phrase": "Обмерзает внутренний блок",
        "document_wording": "Образование инея или льда на теплообменнике внутреннего блока.",
        "likely_diagnosis": "Недостаток хладагента, загрязнение фильтров/теплообменника, ограничение воздушного потока или неисправность датчика.",
        "is_favorite": False,
        "sort_order": 70,
    },
]


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "repair_complaint_preset" not in _tables():
        op.create_table(
            "repair_complaint_preset",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("complaint_group", sa.String(), nullable=False, server_default=""),
            sa.Column("customer_phrase", sa.String(), nullable=False),
            sa.Column("document_wording", sa.String(), nullable=False, server_default=""),
            sa.Column("likely_diagnosis", sa.String(), nullable=False, server_default=""),
            sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("comment", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_repair_complaint_preset_complaint_group"), "repair_complaint_preset", ["complaint_group"], unique=False)
        op.create_index(op.f("ix_repair_complaint_preset_customer_phrase"), "repair_complaint_preset", ["customer_phrase"], unique=False)
        op.create_index(op.f("ix_repair_complaint_preset_is_active"), "repair_complaint_preset", ["is_active"], unique=False)
        op.create_index(op.f("ix_repair_complaint_preset_is_favorite"), "repair_complaint_preset", ["is_favorite"], unique=False)
        op.create_index(op.f("ix_repair_complaint_preset_sort_order"), "repair_complaint_preset", ["sort_order"], unique=False)

    bind = op.get_bind()
    for preset in PRESETS:
        existing_id = bind.execute(
            sa.text(
                """
                SELECT id
                FROM repair_complaint_preset
                WHERE lower(trim(complaint_group)) = lower(trim(:complaint_group))
                  AND lower(trim(customer_phrase)) = lower(trim(:customer_phrase))
                LIMIT 1
                """
            ),
            preset,
        ).scalar_one_or_none()
        if existing_id is not None:
            continue
        bind.execute(
            sa.text(
                """
                INSERT INTO repair_complaint_preset (
                    complaint_group, customer_phrase, document_wording, likely_diagnosis,
                    is_favorite, is_active, sort_order
                ) VALUES (
                    :complaint_group, :customer_phrase, :document_wording, :likely_diagnosis,
                    :is_favorite, true, :sort_order
                )
                """
            ),
            preset,
        )


def downgrade() -> None:
    if "repair_complaint_preset" in _tables():
        op.drop_index(op.f("ix_repair_complaint_preset_sort_order"), table_name="repair_complaint_preset")
        op.drop_index(op.f("ix_repair_complaint_preset_is_favorite"), table_name="repair_complaint_preset")
        op.drop_index(op.f("ix_repair_complaint_preset_is_active"), table_name="repair_complaint_preset")
        op.drop_index(op.f("ix_repair_complaint_preset_customer_phrase"), table_name="repair_complaint_preset")
        op.drop_index(op.f("ix_repair_complaint_preset_complaint_group"), table_name="repair_complaint_preset")
        op.drop_table("repair_complaint_preset")
