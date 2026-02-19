/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DashboardStatsResponse } from '../models/DashboardStatsResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerDashboardService {
    /**
     * Get Dashboard Stats
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
