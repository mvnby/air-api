"""Scalar equivalent of Order.calculate_totals, with independently aggregated joins."""

from sqlalchemy import Numeric, and_, case, cast, func, or_, select
from models import (
    Order,
    OrderInstaller,
    OrderProductLink,
    OrderProposal,
    OrderServiceLink,
    Payment,
)


def board_money(visible_ids):
    """All intermediate relations are fenced by the caller's visible order IDs.

    Round the unit before multiplying, choose the selected active proposal (or
    first active), and fall back to all lines if no active proposal exists.
    Payment conversion uses the computed amount; clamp each debt before grouping.
    This projection never writes or repairs cached model fields.
    """
    ranked = (
        select(
            OrderProposal.order_id,
            OrderProposal.id,
            func.row_number()
            .over(
                partition_by=OrderProposal.order_id,
                order_by=(
                    OrderProposal.is_selected.desc(),
                    OrderProposal.sort_order,
                    OrderProposal.id,
                ),
            )
            .label("rank"),
        )
        .join(visible_ids, visible_ids.c.id == OrderProposal.order_id)
        .where(OrderProposal.is_archived.is_(False))
        .cte("board_ranked_proposals")
    )
    chosen = (
        select(ranked.c.order_id, ranked.c.id)
        .where(ranked.c.rank == 1)
        .cte("board_chosen_proposal")
    )

    def lines(model, name):
        return (
            select(
                model.order_id,
                func.sum(
                    func.round(cast(model.price, Numeric), 2) * model.quantity
                ).label("amount"),
                func.sum(
                    func.round(cast(model.cost, Numeric), 2) * model.quantity
                ).label("cost"),
            )
            .join(visible_ids, visible_ids.c.id == model.order_id)
            .outerjoin(chosen, chosen.c.order_id == model.order_id)
            .where(or_(chosen.c.id.is_(None), model.proposal_id == chosen.c.id))
            .group_by(model.order_id)
            .cte(name)
        )

    products = lines(OrderProductLink, "board_product_money")
    services = lines(OrderServiceLink, "board_service_money")
    installers = (
        select(
            OrderInstaller.order_id, func.sum(OrderInstaller.agreed_pay).label("cost")
        )
        .join(visible_ids, visible_ids.c.id == OrderInstaller.order_id)
        .group_by(OrderInstaller.order_id)
        .cte("board_installer_money")
    )
    payments = (
        select(
            Payment.order_id, Payment.currency, func.sum(Payment.amount).label("amount")
        )
        .join(visible_ids, visible_ids.c.id == Payment.order_id)
        .group_by(Payment.order_id, Payment.currency)
        .cte("board_payment_currency")
    )
    amount = func.coalesce(products.c.amount, 0) + func.coalesce(services.c.amount, 0)
    installer_cost = func.coalesce(installers.c.cost, 0) + func.coalesce(
        Order.worker_pay_cost_byn, 0
    )
    cost = (
        func.coalesce(products.c.cost, 0)
        + func.coalesce(services.c.cost, 0)
        + installer_cost
    )
    totals = (
        select(
            Order.id,
            amount.label("total_amount"),
            cost.label("total_cost"),
            installer_cost.label("installer_cost_byn"),
            (amount - cost).label("margin"),
            Order.target_currency,
            Order.target_currency_amount,
        )
        .join(visible_ids, visible_ids.c.id == Order.id)
        .outerjoin(products, products.c.order_id == Order.id)
        .outerjoin(services, services.c.order_id == Order.id)
        .outerjoin(installers, installers.c.order_id == Order.id)
        .cte("board_totals")
    )
    rate = case(
        (
            and_(
                totals.c.target_currency.is_not(None),
                totals.c.target_currency_amount > 0,
            ),
            totals.c.total_amount / func.nullif(totals.c.target_currency_amount, 0),
        ),
        else_=1.0,
    )
    converted = (
        select(
            totals.c.id,
            func.coalesce(
                func.sum(
                    case(
                        (payments.c.currency == "BYN", payments.c.amount),
                        (
                            and_(
                                payments.c.currency == totals.c.target_currency,
                                rate > 0,
                            ),
                            payments.c.amount * rate,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("total_payments"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                payments.c.currency == "BYN",
                                totals.c.target_currency.is_not(None),
                                rate > 0,
                            ),
                            payments.c.amount / func.nullif(rate, 0),
                        ),
                        (
                            and_(
                                payments.c.currency != "BYN",
                                payments.c.currency == totals.c.target_currency,
                            ),
                            payments.c.amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("target_currency_payments"),
        )
        .select_from(totals)
        .outerjoin(payments, payments.c.order_id == totals.c.id)
        .group_by(
            totals.c.id,
            totals.c.total_amount,
            totals.c.target_currency,
            totals.c.target_currency_amount,
        )
        .cte("board_converted_payments")
    )
    return (
        select(
            totals.c.id,
            totals.c.total_amount,
            totals.c.total_cost,
            totals.c.margin,
            totals.c.installer_cost_byn,
            converted.c.total_payments,
            converted.c.target_currency_payments,
            func.greatest(0, totals.c.total_amount - converted.c.total_payments).label(
                "balance_due"
            ),
        )
        .join(converted, converted.c.id == totals.c.id)
        .cte("board_money")
    )
