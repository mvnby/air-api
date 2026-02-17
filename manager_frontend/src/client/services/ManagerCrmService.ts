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
