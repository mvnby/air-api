"""expand estimate and order service money without narrowing legacy values

Revision ID: e68b7c9d0e1f
Revises: e67a7b8c9d0f
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import sqlalchemy as sa
from alembic import op


revision = "e68b7c9d0e1f"
down_revision = "e67a7b8c9d0f"
branch_labels = None
depends_on = None

_CENT = Decimal("0.01")
_FLOAT_DUST = Decimal("0.0000001")


def _cent(value: object) -> Decimal:
    try:
        number = Decimal(str(value))
        rounded = number.quantize(_CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("non-finite or invalid money") from exc
    if not number.is_finite() or abs(number - rounded) > _FLOAT_DUST:
        raise ValueError("value cannot be represented to cents")
    return rounded


def _preflight_estimates(connection: sa.Connection) -> None:
    blockers: list[str] = []
    rows = connection.execution_options(stream_results=True).execute(sa.text("""
        SELECT e.id, e.subtotal, e.discount_amount, e.total,
               COALESCE(SUM(i.line_total), 0) AS items_total
        FROM service_estimate e
        LEFT JOIN service_estimate_item i ON i.estimate_id = e.id
        GROUP BY e.id, e.subtotal, e.discount_amount, e.total
    """))
    for row in rows:
        try:
            subtotal = _cent(row.subtotal)
            discount = _cent(row.discount_amount)
            total = _cent(row.total)
            item_sum = _cent(row.items_total)
            if min(subtotal, discount, total) < 0 or discount > subtotal:
                raise ValueError("negative or excessive discount")
            if subtotal - discount != total or item_sum != subtotal:
                raise ValueError("snapshot totals do not reconcile")
        except ValueError as exc:
            blockers.append(f"estimate {row.id}: {exc}")
            if len(blockers) >= 10:
                break
    rows.close()

    if not blockers:
        rows = connection.execution_options(stream_results=True).execute(
            sa.text("SELECT id, line_total FROM service_estimate_item")
        )
        for row in rows:
            try:
                if _cent(row.line_total) < 0:
                    raise ValueError("negative line total")
            except ValueError as exc:
                blockers.append(f"estimate item {row.id}: {exc}")
                if len(blockers) >= 10:
                    break
        rows.close()
    if blockers:
        raise RuntimeError(
            "Estimate money preflight blocked schema expansion; review the saved snapshots "
            "without changing historical documents: " + "; ".join(blockers)
        )


def _expand(table: str, names: tuple[str, ...], existing_type: sa.types.TypeEngine) -> None:
    if op.get_bind().dialect.name == "postgresql":
        for name in names:
            op.alter_column(
                table, name, existing_type=existing_type, type_=sa.Numeric(),
                existing_nullable=False, postgresql_using=f"{name}::numeric",
            )
    else:
        with op.batch_alter_table(table) as batch:
            for name in names:
                batch.alter_column(
                    name, existing_type=existing_type, type_=sa.Numeric(),
                    existing_nullable=False,
                )


def upgrade() -> None:
    connection = op.get_bind()
    _preflight_estimates(connection)
    _expand("service_estimate", ("subtotal", "discount_amount", "total"), sa.Float())
    _expand("service_estimate_item", ("line_total",), sa.Float())
    _expand("order_service_link", ("price", "cost"), sa.Integer())


def downgrade() -> None:
    raise RuntimeError(
        "Money precision expansion is roll-forward only: downgrading order service "
        "prices to integers would discard cents"
    )
