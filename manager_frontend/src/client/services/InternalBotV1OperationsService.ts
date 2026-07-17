/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotCuratedProductsRequest } from '../models/BotCuratedProductsRequest';
import type { BotCuratedProductsResponse } from '../models/BotCuratedProductsResponse';
import type { BotProductMutationRequest } from '../models/BotProductMutationRequest';
import type { BotProductMutationResponse } from '../models/BotProductMutationResponse';
import type { BotProductPriceUpdateRequest } from '../models/BotProductPriceUpdateRequest';
import type { BotProductSelectionRequest } from '../models/BotProductSelectionRequest';
import type { BotProductSelectionResponse } from '../models/BotProductSelectionResponse';
import type { BotRepairApplyRequest } from '../models/BotRepairApplyRequest';
import type { BotRepairApplyResponse } from '../models/BotRepairApplyResponse';
import type { BotRepairDraftRequest } from '../models/BotRepairDraftRequest';
import type { BotRepairDraftResponse } from '../models/BotRepairDraftResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class InternalBotV1OperationsService {
    /**
     * Build Catalog Selection
     * @param requestBody
     * @returns BotProductSelectionResponse Successful Response
     * @throws ApiError
     */
    public static buildInternalBotCatalogSelectionV1(
        requestBody: BotProductSelectionRequest,
    ): CancelablePromise<BotProductSelectionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/catalog/selection',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Curated Catalog
     * @param requestBody
     * @returns BotCuratedProductsResponse Successful Response
     * @throws ApiError
     */
    public static getInternalBotCuratedCatalogV1(
        requestBody: BotCuratedProductsRequest,
    ): CancelablePromise<BotCuratedProductsResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/catalog/curated',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Catalog Product Price
     * @param productId
     * @param requestBody
     * @returns BotProductMutationResponse Successful Response
     * @throws ApiError
     */
    public static updateInternalBotCatalogProductPriceV1(
        productId: number,
        requestBody: BotProductPriceUpdateRequest,
    ): CancelablePromise<BotProductMutationResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/catalog/products/{product_id}/price',
            path: {
                'product_id': productId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Catalog Product
     * @param productId
     * @param requestBody
     * @returns BotProductMutationResponse Successful Response
     * @throws ApiError
     */
    public static deleteInternalBotCatalogProductV1(
        productId: number,
        requestBody: BotProductMutationRequest,
    ): CancelablePromise<BotProductMutationResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/catalog/products/{product_id}/delete',
            path: {
                'product_id': productId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Build Repair Comment Draft
     * @param requestBody
     * @returns BotRepairDraftResponse Successful Response
     * @throws ApiError
     */
    public static buildInternalBotRepairCommentDraftV1(
        requestBody: BotRepairDraftRequest,
    ): CancelablePromise<BotRepairDraftResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/repair-context/comment-draft',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Build Repair Preset Draft
     * @param requestBody
     * @returns BotRepairDraftResponse Successful Response
     * @throws ApiError
     */
    public static buildInternalBotRepairPresetDraftV1(
        requestBody: BotRepairDraftRequest,
    ): CancelablePromise<BotRepairDraftResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/repair-context/preset-draft',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Apply Repair Context
     * @param requestBody
     * @returns BotRepairApplyResponse Successful Response
     * @throws ApiError
     */
    public static applyInternalBotRepairContextV1(
        requestBody: BotRepairApplyRequest,
    ): CancelablePromise<BotRepairApplyResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/repair-context/apply',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
