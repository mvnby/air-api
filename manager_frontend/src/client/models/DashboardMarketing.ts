/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DashboardMarketingSource } from './DashboardMarketingSource';
export type DashboardMarketing = {
    status: 'unconfigured' | 'fresh' | 'stale' | 'error';
    provider?: string;
    visits?: (number | null);
    sources?: Array<DashboardMarketingSource>;
    ad_spend?: (number | null);
    clicks?: (number | null);
    impressions?: (number | null);
    ctr?: (number | null);
    leads?: (number | null);
    cost_per_lead?: (number | null);
    customer_acquisition_cost?: (number | null);
    updated_at?: (string | null);
    message?: (string | null);
};

