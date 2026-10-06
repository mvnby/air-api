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
     * Build a product selection from the Manager actor’s text query using the shared catalog.
     * Active Manager access is required (403); invalid selection input returns 422. This read
     * does not create an order.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
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
     * Read curated shared catalog products by area, inverter choice and tags for an active
     * staff actor (403 otherwise). Invalid selection input returns 422; response is bounded by
     * limit.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
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
     * Set an absolute shared product price for an active Manager actor (403 otherwise).
     * Returns changed from the product service; invalid values return 422. It does not change
     * a tenant-specific storefront offer price.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
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
     * Delete a shared product for an active Manager actor (403 otherwise), returning the
     * product service changed result. Invalid service input returns 422; this is a catalog
     * mutation, not a storefront unpublish operation.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
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
     * Build a diagnostic repair draft from comment text for a system-tenant repair order
     * accessible to the active staff actor. Does not apply the draft. Non-staff return 403,
     * unavailable order 404 and invalid input 422.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
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
     * Build a diagnostic repair draft from a fault preset for an accessible system-tenant
     * repair order. Requires active staff (403); unavailable order returns 404 and invalid
     * input 422. The draft must be applied separately.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
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
     * Apply diagnostic draft metadata and raw comment to an accessible system-tenant repair
     * order, carrying optional Telegram provenance. Requires active staff (403); unavailable
     * order returns 404 and invalid input 422. This action persists repair context.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
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
