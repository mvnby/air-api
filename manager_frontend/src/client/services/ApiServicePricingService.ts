/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { InstallationPreviewPayload } from '../models/InstallationPreviewPayload';
import type { InstallationPreviewResponse } from '../models/InstallationPreviewResponse';
import type { InstallationResolvePayload } from '../models/InstallationResolvePayload';
import type { InstallationResolveResponse } from '../models/InstallationResolveResponse';
import type { ManagerInstallEstimateResponse } from '../models/ManagerInstallEstimateResponse';
import type { ManagerTariffServiceKind } from '../models/ManagerTariffServiceKind';
import type { PublicServiceEstimateCalculatePayload } from '../models/PublicServiceEstimateCalculatePayload';
import type { PublicServiceTariffListResponse } from '../models/PublicServiceTariffListResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ApiServicePricingService {
    /**
     * Resolve Public Installation Tariff
     * @param requestBody
     * @returns InstallationResolveResponse Successful Response
     * @throws ApiError
     */
    public static resolvePublicInstallationTariff(
        requestBody: InstallationResolvePayload,
    ): CancelablePromise<InstallationResolveResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/service-pricing/installation/resolve',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Preview Public Installation Estimate
     * @param requestBody
     * @returns InstallationPreviewResponse Successful Response
     * @throws ApiError
     */
    public static previewPublicInstallationEstimate(
        requestBody: InstallationPreviewPayload,
    ): CancelablePromise<InstallationPreviewResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/service-pricing/installation/preview',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
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
