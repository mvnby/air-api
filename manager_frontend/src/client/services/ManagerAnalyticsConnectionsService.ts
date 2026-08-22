/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AnalyticsConnectionItem } from '../models/AnalyticsConnectionItem';
import type { AnalyticsConnectionListResponse } from '../models/AnalyticsConnectionListResponse';
import type { YandexMetrikaConnectionUpsertPayload } from '../models/YandexMetrikaConnectionUpsertPayload';
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
}
