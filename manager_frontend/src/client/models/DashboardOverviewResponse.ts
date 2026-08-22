/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DashboardFunnelStage } from './DashboardFunnelStage';
import type { DashboardKpis } from './DashboardKpis';
import type { DashboardMarketing } from './DashboardMarketing';
import type { DashboardPeriod } from './DashboardPeriod';
import type { DashboardSalesSeriesPoint } from './DashboardSalesSeriesPoint';
export type DashboardOverviewResponse = {
    generated_at: string;
    period: DashboardPeriod;
    kpis: DashboardKpis;
    sales_series: Array<DashboardSalesSeriesPoint>;
    funnel: Array<DashboardFunnelStage>;
    marketing: DashboardMarketing;
};

