/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerInstallEstimateCalculatePayload } from '../models/ManagerInstallEstimateCalculatePayload';
import type { ManagerInstallEstimateResponse } from '../models/ManagerInstallEstimateResponse';
import type { ManagerInstallEstimateSavePayload } from '../models/ManagerInstallEstimateSavePayload';
import type { ManagerServiceEstimateListResponse } from '../models/ManagerServiceEstimateListResponse';
import type { ManagerServiceEstimateResponse } from '../models/ManagerServiceEstimateResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerServiceEstimatesService {
    /**
     * Calculate Manager Install Estimate
     * @param requestBody
     * @returns ManagerInstallEstimateResponse Successful Response
     * @throws ApiError
     */
    public static calculateManagerInstallEstimate(
        requestBody: ManagerInstallEstimateCalculatePayload,
    ): CancelablePromise<ManagerInstallEstimateResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/service-estimates/calculate',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Manager Service Estimate
     * @param requestBody
     * @returns ManagerServiceEstimateResponse Successful Response
     * @throws ApiError
     */
    public static createManagerServiceEstimate(
        requestBody: ManagerInstallEstimateSavePayload,
    ): CancelablePromise<ManagerServiceEstimateResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/service-estimates',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Manager Service Estimates
     * @param page
     * @param limit
     * @returns ManagerServiceEstimateListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerServiceEstimates(
        page: number = 1,
        limit: number = 20,
    ): CancelablePromise<ManagerServiceEstimateListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/service-estimates',
            query: {
                'page': page,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Manager Service Estimate
     * @param estimateId
     * @returns ManagerServiceEstimateResponse Successful Response
     * @throws ApiError
     */
    public static getManagerServiceEstimate(
        estimateId: number,
    ): CancelablePromise<ManagerServiceEstimateResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/service-estimates/{estimate_id}',
            path: {
                'estimate_id': estimateId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
