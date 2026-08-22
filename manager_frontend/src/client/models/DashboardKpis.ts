/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DashboardKpi } from './DashboardKpi';
export type DashboardKpis = {
    /**
     * Actual BYN Payment.amount grouped by Payment.date.
     */
    revenue: DashboardKpi;
    /**
     * Canonical Lead rows grouped by Lead.created_at; legacy order inbox rows are not double-counted.
     */
    new_leads: DashboardKpi;
    /**
     * Orders closed as won, grouped strictly by Order.closed_at.
     */
    sales: DashboardKpi;
    /**
     * Completed work stages named 'Монтаж' (trimmed, case-insensitive), grouped by end_time and falling back to the parent order updated_at proxy.
     */
    installations: DashboardKpi;
    /**
     * Current active lead/order touchpoint backlog; historical snapshot is unavailable.
     */
    active_tasks: DashboardKpi;
    /**
     * Current positive balance_due snapshot across all BYN negotiation/execution orders; historical snapshot is unavailable.
     */
    receivables: DashboardKpi;
};

