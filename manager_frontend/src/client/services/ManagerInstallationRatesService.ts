/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerInstallationRateListResponse } from '../models/ManagerInstallationRateListResponse';
import type { ManagerInstallationRateResponse } from '../models/ManagerInstallationRateResponse';
import type { ManagerInstallationRateUpdatePayload } from '../models/ManagerInstallationRateUpdatePayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerInstallationRatesService {
    /**
     * List Manager Installation Rates
     * @returns ManagerInstallationRateListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerInstallationRates(): CancelablePromise<ManagerInstallationRateListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/installation-rates',
        });
    }
    /**
     * Update Manager Installation Rate
     * @param rateId
     * @param requestBody
     * @returns ManagerInstallationRateResponse Successful Response
     * @throws ApiError
     */
    public static updateManagerInstallationRate(
        rateId: number,
        requestBody: ManagerInstallationRateUpdatePayload,
    ): CancelablePromise<ManagerInstallationRateResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/installation-rates/{rate_id}',
            path: {
                'rate_id': rateId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
