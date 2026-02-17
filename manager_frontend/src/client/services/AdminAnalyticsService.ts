/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class AdminAnalyticsService {
    /**
     * Get Dashboard Stats
     * Dashboard stats endpoint - uses session-based auth (called from admin panel AJAX).
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getDashboardStatsAdminStatsGet(): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/admin/stats',
        });
    }
}
