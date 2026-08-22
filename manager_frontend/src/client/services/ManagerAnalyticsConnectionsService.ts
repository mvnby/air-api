/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AnalyticsAuthorizationUrlResponse } from '../models/AnalyticsAuthorizationUrlResponse';
import type { AnalyticsConnectionItem } from '../models/AnalyticsConnectionItem';
import type { AnalyticsConnectionListResponse } from '../models/AnalyticsConnectionListResponse';
import type { GoogleAdsAuthorizationPayload } from '../models/GoogleAdsAuthorizationPayload';
import type { GoogleAnalyticsAuthorizationPayload } from '../models/GoogleAnalyticsAuthorizationPayload';
import type { YandexDirectConnectionUpsertPayload } from '../models/YandexDirectConnectionUpsertPayload';
import type { YandexMetrikaConnectionUpsertPayload } from '../models/YandexMetrikaConnectionUpsertPayload';
import type { YandexWebmasterConnectionUpsertPayload } from '../models/YandexWebmasterConnectionUpsertPayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerAnalyticsConnectionsService {
    /**
     * List Manager Analytics Connections
     * @returns AnalyticsConnectionListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerAnalyticsConnections(): CancelablePromise<AnalyticsConnectionListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/analytics-connections',
        });
    }
    /**
     * Upsert Manager Yandex Metrika Connection
     * @param requestBody
     * @returns AnalyticsConnectionItem Successful Response
     * @throws ApiError
     */
    public static upsertManagerYandexMetrikaConnection(
        requestBody: YandexMetrikaConnectionUpsertPayload,
    ): CancelablePromise<AnalyticsConnectionItem> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/analytics-connections/yandex-metrika',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Upsert Manager Yandex Direct Connection
     * @param requestBody
     * @returns AnalyticsConnectionItem Successful Response
     * @throws ApiError
     */
    public static upsertManagerYandexDirectConnection(
        requestBody: YandexDirectConnectionUpsertPayload,
    ): CancelablePromise<AnalyticsConnectionItem> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/analytics-connections/yandex-direct',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Upsert Manager Yandex Webmaster Connection
     * @param requestBody
     * @returns AnalyticsConnectionItem Successful Response
     * @throws ApiError
     */
    public static upsertManagerYandexWebmasterConnection(
        requestBody: YandexWebmasterConnectionUpsertPayload,
    ): CancelablePromise<AnalyticsConnectionItem> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/analytics-connections/yandex-webmaster',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Start Manager Google Analytics Authorization
     * @param requestBody
     * @returns AnalyticsAuthorizationUrlResponse Successful Response
     * @throws ApiError
     */
    public static startManagerGoogleAnalyticsAuthorization(
        requestBody: GoogleAnalyticsAuthorizationPayload,
    ): CancelablePromise<AnalyticsAuthorizationUrlResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/analytics-connections/google-analytics/authorization-url',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Start Manager Google Search Console Authorization
     * @returns AnalyticsAuthorizationUrlResponse Successful Response
     * @throws ApiError
     */
    public static startManagerGoogleSearchConsoleAuthorization(): CancelablePromise<AnalyticsAuthorizationUrlResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/analytics-connections/google-search-console/authorization-url',
        });
    }
    /**
     * Start Manager Google Ads Authorization
     * @param requestBody
     * @returns AnalyticsAuthorizationUrlResponse Successful Response
     * @throws ApiError
     */
    public static startManagerGoogleAdsAuthorization(
        requestBody: GoogleAdsAuthorizationPayload,
    ): CancelablePromise<AnalyticsAuthorizationUrlResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/analytics-connections/google-ads/authorization-url',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
