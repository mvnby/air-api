/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerInstallEstimateResponse } from '../models/ManagerInstallEstimateResponse';
import type { ManagerTariffServiceKind } from '../models/ManagerTariffServiceKind';
import type { PublicServiceEstimateCalculatePayload } from '../models/PublicServiceEstimateCalculatePayload';
import type { PublicServiceTariffListResponse } from '../models/PublicServiceTariffListResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ApiServicePricingService {
    /**
     * List Public Service Tariffs
     * @param serviceKind
     * @returns PublicServiceTariffListResponse Successful Response
     * @throws ApiError
     */
    public static listPublicServiceTariffs(
        serviceKind: ManagerTariffServiceKind,
    ): CancelablePromise<PublicServiceTariffListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/service-pricing/tariffs',
            query: {
                'service_kind': serviceKind,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Calculate Public Service Tariff
     * @param requestBody
     * @returns ManagerInstallEstimateResponse Successful Response
     * @throws ApiError
     */
    public static calculatePublicServiceTariff(
        requestBody: PublicServiceEstimateCalculatePayload,
    ): CancelablePromise<ManagerInstallEstimateResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/service-pricing/calculate',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
