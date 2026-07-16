/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotApiHealthResponse } from '../models/BotApiHealthResponse';
import type { BotCatalogProductLookupResponse } from '../models/BotCatalogProductLookupResponse';
import type { BotCatalogSearchRequest } from '../models/BotCatalogSearchRequest';
import type { BotCatalogSearchResponse } from '../models/BotCatalogSearchResponse';
import type { BotStaffContextResponse } from '../models/BotStaffContextResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class InternalBotV1Service {
    /**
     * Get Internal Bot Api Health
     * @returns BotApiHealthResponse Successful Response
     * @throws ApiError
     */
    public static getInternalBotApiHealthV1(): CancelablePromise<BotApiHealthResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/internal/bot/v1/health',
        });
    }
    /**
     * Get Internal Bot Staff Context
     * @param telegramId
     * @returns BotStaffContextResponse Successful Response
     * @throws ApiError
     */
    public static getInternalBotStaffContextV1(
        telegramId: number,
    ): CancelablePromise<BotStaffContextResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/internal/bot/v1/staff/context/{telegram_id}',
            path: {
                'telegram_id': telegramId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Search Internal Bot Catalog
     * @param requestBody
     * @returns BotCatalogSearchResponse Successful Response
     * @throws ApiError
     */
    public static searchInternalBotCatalogV1(
        requestBody: BotCatalogSearchRequest,
    ): CancelablePromise<BotCatalogSearchResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/catalog/search',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Internal Bot Catalog Product
     * @param productId
     * @param telegramId
     * @returns BotCatalogProductLookupResponse Successful Response
     * @throws ApiError
     */
    public static getInternalBotCatalogProductV1(
        productId: number,
        telegramId: number,
    ): CancelablePromise<BotCatalogProductLookupResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/internal/bot/v1/catalog/products/{product_id}',
            path: {
                'product_id': productId,
            },
            query: {
                'telegram_id': telegramId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
