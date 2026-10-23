"""Shared membership rules for dashboard aggregates and their record lists."""

from sqlalchemy import func, or_

from models.common import ClosingResult, LeadStatus, OrderStageStatus, OrderStatus, PaymentCurrency
from models.customer import Lead
from models.order import Order, OrderWorkStage, Payment
from services.order_financial_eligibility import collectible_order_clause, financially_committed_order_clause
from services.tenant_scope_service import storefront_scope_clause


def revenue_conditions(scope, bounds):
    return (
        storefront_scope_clause(Order, scope), financially_committed_order_clause(),
        Payment.currency == PaymentCurrency.BYN,
        Payment.date >= bounds[0], Payment.date < bounds[1],
    )


def lead_conditions(scope, bounds):
    return (
        storefront_scope_clause(Lead, scope),
        Lead.created_at >= bounds[0], Lead.created_at < bounds[1],
    )


def sales_conditions(scope, bounds):
    return (
        storefront_scope_clause(Order, scope), Order.status == OrderStatus.CLOSED,
        Order.closing_result == ClosingResult.WON.value, Order.closed_at.is_not(None),
        Order.closed_at >= bounds[0], Order.closed_at < bounds[1],
    )


def installation_completed_at():
    return func.coalesce(OrderWorkStage.end_time, Order.updated_at)


def installation_conditions(scope, bounds):
    completed_at = installation_completed_at()
    return (
        storefront_scope_clause(Order, scope), Order.workflow_type == "sales_installation",
        OrderWorkStage.status == OrderStageStatus.COMPLETED,
        func.lower(func.trim(OrderWorkStage.name)) == "монтаж",
        completed_at >= bounds[0], completed_at < bounds[1],
    )


def order_touchpoint_conditions(scope):
    return (
        storefront_scope_clause(Order, scope), Order.status != OrderStatus.CLOSED,
        Order.next_followup_date.is_not(None),
    )


def lead_touchpoint_conditions(scope):
    return (
        storefront_scope_clause(Lead, scope),
        Lead.status.in_([LeadStatus.new, LeadStatus.contacted]),
        Lead.next_followup_date.is_not(None),
    )


def receivable_conditions(scope):
    return (
        storefront_scope_clause(Order, scope), collectible_order_clause(), Order.balance_due > 0,
        or_(Order.target_currency.is_(None), Order.target_currency == PaymentCurrency.BYN),
    )
