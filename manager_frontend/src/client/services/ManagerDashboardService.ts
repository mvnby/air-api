/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DashboardOverviewResponse } from '../models/DashboardOverviewResponse';
import type { DashboardStatsResponse } from '../models/DashboardStatsResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerDashboardService {
    /**
     * Get Dashboard Overview
     * Build the current storefront's Manager dashboard for the current month and comparable
     * previous-month window. Includes canonical Lead counts, revenue, sales, installation stages,
     * funnel and configured external marketing/search indicators. Follow-ups and receivables are
     * current-state snapshots without previous-period values. Tenant/storefront scope comes from
     * authenticated Manager access; provider availability is represented in the dashboard result.
     * This is an aggregate report, not a ledger export.
     * @returns DashboardOverviewResponse Successful Response
     * @throws ApiError
     */
    public static getManagerDashboardOverview(): CancelablePromise<DashboardOverviewResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/dashboard/overview',
        });
    }
    /**
     * Get Dashboard Stats
     * Read the legacy Manager dashboard summary scoped to the current storefront and accessible
     * tenant customers. Closed-deal amount and new-lead counts use Order rows created since the
     * start of the current month; these differ from the canonical Lead funnel in /overview. Also
     * returns bounded follow-up and tenant contract-expiry summaries; platform-wide bank-receipt
     * review appears only for system-tenant access. Requires Manager access; does not modify
     * orders or allocate payments.
     * @returns DashboardStatsResponse Successful Response
     * @throws ApiError
     */
    public static getDashboardStats(): CancelablePromise<DashboardStatsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/dashboard/stats',
        });
    }
}
