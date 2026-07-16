/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerActionMessageResponse } from '../models/ManagerActionMessageResponse';
import type { ManagerInstallEstimateCalculatePayload } from '../models/ManagerInstallEstimateCalculatePayload';
import type { ManagerInstallEstimateResponse } from '../models/ManagerInstallEstimateResponse';
import type { ManagerInstallEstimateSavePayload } from '../models/ManagerInstallEstimateSavePayload';
import type { ManagerServiceDescriptionMode } from '../models/ManagerServiceDescriptionMode';
import type { ManagerServiceEstimateListResponse } from '../models/ManagerServiceEstimateListResponse';
import type { ManagerServiceEstimateOrderLinesMode } from '../models/ManagerServiceEstimateOrderLinesMode';
import type { ManagerServiceEstimateOrderLinesResponse } from '../models/ManagerServiceEstimateOrderLinesResponse';
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
     * @param customerId
     * @returns ManagerServiceEstimateListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerServiceEstimates(
        page: number = 1,
        limit: number = 20,
        customerId?: (number | null),
    ): CancelablePromise<ManagerServiceEstimateListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/service-estimates',
            query: {
                'page': page,
                'limit': limit,
                'customer_id': customerId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Manager Service Estimate Order Lines
     * @param estimateId
     * @param mode
     * @param descriptionMode
     * @returns ManagerServiceEstimateOrderLinesResponse Successful Response
     * @throws ApiError
     */
    public static getManagerServiceEstimateOrderLines(
        estimateId: number,
        mode: ManagerServiceEstimateOrderLinesMode = 'detailed',
        descriptionMode: ManagerServiceDescriptionMode = 'short',
    ): CancelablePromise<ManagerServiceEstimateOrderLinesResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/service-estimates/{estimate_id}/order-lines',
            path: {
                'estimate_id': estimateId,
            },
            query: {
                'mode': mode,
                'description_mode': descriptionMode,
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
    /**
     * Delete Manager Service Estimate
     * @param estimateId
     * @returns ManagerActionMessageResponse Successful Response
     * @throws ApiError
     */
    public static deleteManagerServiceEstimate(
        estimateId: number,
    ): CancelablePromise<ManagerActionMessageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
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
