/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { InstallationPreviewPayload } from '../models/InstallationPreviewPayload';
import type { InstallationPreviewResponse } from '../models/InstallationPreviewResponse';
import type { InstallationPricingConfigResponse } from '../models/InstallationPricingConfigResponse';
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
     * Get Public Installation Pricing Config
     * Tell the storefront which installation pricing contract is authoritative. Response uses
     * private/no-store headers; read this before choosing legacy calculation or price-book
     * preview.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @returns InstallationPricingConfigResponse Successful Response
     * @throws ApiError
     */
    public static getPublicInstallationPricingConfig(): CancelablePromise<InstallationPricingConfigResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/service-pricing/installation/config',
        });
    }
    /**
     * Resolve Public Installation Tariff
     * Resolve a tariff using the storefront installation price book. Disabled installation is
     * reported as status=unavailable with service_direction_not_enabled, rather than 404. Does
     * not create an order.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
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
     * Calculate a price-book installation preview and, outside read-only demo scope, persist
     * its receipt using the required Idempotency-Key. Public callers cannot approve site
     * access: approved_site_access returns 422. Disabled installation returns
     * status=unavailable. A persistent preview replays the same input/key for its 30-minute
     * receipt lifetime; another input with that key returns 409 idempotency_key_reused. A
     * price-book revision mismatch returns 409 price_changed. Receipt
     * contention/unavailability can return 503 with Retry-After: 1; retain the same input/key
     * for a retry. Preview is not acceptance or order creation.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @param idempotencyKey
     * @param requestBody
     * @returns InstallationPreviewResponse Successful Response
     * @throws ApiError
     */
    public static previewPublicInstallationEstimate(
        idempotencyKey: string,
        requestBody: InstallationPreviewPayload,
    ): CancelablePromise<InstallationPreviewResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/service-pricing/installation/preview',
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Public Service Tariffs
     * List active service tariffs and active rules for this storefront and service direction.
     * Disabled direction returns 404; installation backed by a published price book returns
     * 409 book_preview_required.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
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
     * Calculate a legacy active tariff within this storefront without creating an order.
     * Disabled service direction returns 404; installation with a published price book returns
     * 409 book_preview_required. Tariff access and active status are checked by the tariff
     * service.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
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
