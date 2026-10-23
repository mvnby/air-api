/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DashboardDetailItem } from './DashboardDetailItem';
import type { DashboardPeriodRange } from './DashboardPeriodRange';
export type DashboardDetailResponse = {
    metric: 'revenue' | 'new_leads' | 'sales' | 'installations' | 'active_tasks' | 'receivables';
    items: Array<DashboardDetailItem>;
    total: number;
    value: number;
    unit: 'byn' | 'count';
    limit: number;
    offset: number;
    generated_at: string;
    /**
     * Exact requested period; null for current-state metrics.
     */
    period?: (DashboardPeriodRange | null);
};

