/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DashboardSearchDemandProvider } from './DashboardSearchDemandProvider';
import type { DashboardSearchQuery } from './DashboardSearchQuery';
export type DashboardSearchDemand = {
    status: 'unconfigured' | 'fresh' | 'stale' | 'error';
    queries?: Array<DashboardSearchQuery>;
    providers?: Array<DashboardSearchDemandProvider>;
    updated_at?: (string | null);
    message?: (string | null);
};

