/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerCrmHealthReportResponse } from '../models/ManagerCrmHealthReportResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerCrmService {
    /**
     * Get Manager Crm Health Report
     * Read in-process Manager API error and qualification telemetry over 1 hour–14 days. Route
     * policy requires system-tenant Manager access because these aggregates are platform-wide
     * rather than tenant CRM records. This is a diagnostic snapshot, not durable business
     * history or proof of database health.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param hours
     * @returns ManagerCrmHealthReportResponse Successful Response
     * @throws ApiError
     */
    public static getManagerCrmHealthReport(
        hours: number = 24,
    ): CancelablePromise<ManagerCrmHealthReportResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/crm/health-report',
            query: {
                'hours': hours,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
