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
     * Calculate legacy tariff/rule pricing and discount without saving a ServiceEstimate or
     * adding order lines. Missing/out-of-scope tariff returns 404; inactive tariffs remain
     * addressable by ID, but inactive rules are excluded from calculation. After tenant
     * price-book publication, installation tariffs return 409 book_preview_required while
     * other service kinds remain available. Use published-book preview/confirmation for new
     * typed installation pricing.
     *
     * Access and scope: Manager access is required; service catalog data belongs to the
     * authenticated tenant, independently of storefront. The system tenant also reads legacy
     * rows with NULL tenant ownership. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
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
     * Calculate current legacy tariff/rules and save an independent estimate/item snapshot,
     * optionally linked to a tenant customer. Missing/out-of-scope tariff or inaccessible
     * customer returns 404; inactive tariffs remain addressable by ID. Installation tariffs
     * are blocked with 409 book_preview_required after book publication; other service kinds
     * remain supported. No idempotency receipt exists: each successful call creates a new
     * snapshot and does not attach it to an order.
     *
     * Access and scope: Manager access is required; service catalog data belongs to the
     * authenticated tenant, independently of storefront. The system tenant also reads legacy
     * rows with NULL tenant ownership. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
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
     * Read saved historical service estimates, optionally by customer, with page starting at 1
     * and limit 1–100. Publication of a typed installation price book does not hide prior
     * estimates. Reading uses saved snapshots rather than recalculating current tariffs.
     *
     * Access and scope: Manager access is required; service catalog data belongs to the
     * authenticated tenant, independently of storefront. The system tenant also reads legacy
     * rows with NULL tenant ownership. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
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
     * Project a saved service estimate into collapsed/detailed order-line payloads with
     * short/full descriptions. Missing estimate returns 404; inconsistent totals or amounts
     * outside the writable service-money range return 409. Discount is distributed so
     * projected lines reconcile to the saved total. This only returns a projection and does
     * not insert proposal/order lines.
     *
     * Access and scope: Manager access is required; service catalog data belongs to the
     * authenticated tenant, independently of storefront. The system tenant also reads legacy
     * rows with NULL tenant ownership. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
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
     * Read one saved historical service-estimate snapshot and items. Missing or inaccessible
     * estimate returns 404. Changes to tariff definitions and later price-book publication do
     * not recalculate its saved amounts.
     *
     * Access and scope: Manager access is required; service catalog data belongs to the
     * authenticated tenant, independently of storefront. The system tenant also reads legacy
     * rows with NULL tenant ownership. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
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
     * Permanently delete one saved historical service estimate. Missing or inaccessible
     * estimate returns 404, including after deletion. This is a mutation of saved history, not
     * cancellation of an accepted typed installation estimate or automatic removal of order
     * lines.
     *
     * Access and scope: Manager access is required; service catalog data belongs to the
     * authenticated tenant, independently of storefront. The system tenant also reads legacy
     * rows with NULL tenant ownership. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
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
