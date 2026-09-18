/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { YandexBusinessFeedPreview } from '../models/YandexBusinessFeedPreview';
import type { YandexBusinessFeedQualityReport } from '../models/YandexBusinessFeedQualityReport';
import type { YandexBusinessFeedSettingsPayload } from '../models/YandexBusinessFeedSettingsPayload';
import type { YandexBusinessFeedSettingsResponse } from '../models/YandexBusinessFeedSettingsResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerYandexBusinessService {
    /**
     * Get Manager Yandex Business Feed Settings
     * @returns YandexBusinessFeedSettingsResponse Successful Response
     * @throws ApiError
     */
    public static getManagerYandexBusinessFeedSettings(): CancelablePromise<YandexBusinessFeedSettingsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/yandex-business/settings',
        });
    }
    /**
     * Update Manager Yandex Business Feed Settings
     * @param requestBody
     * @returns YandexBusinessFeedSettingsResponse Successful Response
     * @throws ApiError
     */
    public static updateManagerYandexBusinessFeedSettings(
        requestBody: YandexBusinessFeedSettingsPayload,
    ): CancelablePromise<YandexBusinessFeedSettingsResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/yandex-business/settings',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Preview Manager Yandex Business Feed Settings
     * @param requestBody
     * @returns YandexBusinessFeedPreview Successful Response
     * @throws ApiError
     */
    public static previewManagerYandexBusinessFeedSettings(
        requestBody: YandexBusinessFeedSettingsPayload,
    ): CancelablePromise<YandexBusinessFeedPreview> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/yandex-business/settings/preview',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Manager Yandex Business Price List
     * @returns string Successful Response
     * @throws ApiError
     */
    public static getManagerYandexBusinessPriceList(): CancelablePromise<string> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/yandex-business/price-list.yml',
        });
    }
    /**
     * Get Manager Yandex Business Quality Report
     * @returns YandexBusinessFeedQualityReport Successful Response
     * @throws ApiError
     */
    public static getManagerYandexBusinessQualityReport(): CancelablePromise<YandexBusinessFeedQualityReport> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/yandex-business/quality-report',
        });
    }
}
