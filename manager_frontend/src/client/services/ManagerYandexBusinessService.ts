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
     * Read effective Yandex Business feed settings for the server-resolved system tenant. Requires
     * system-tenant Manager access via route policy. These are
     * canonical platform-feed settings, not settings of the caller's selected storefront. Reading
     * does not publish or change the feed.
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
     * Save the canonical Yandex Business feed configuration for the server-resolved system tenant.
     * Requires a system-tenant owner/admin. The payload replaces the feed settings through the
     * settings service; this does not submit a feed to Yandex or confirm its acceptance. No
     * optimistic version or command replay receipt is provided.
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
     * Build the platform Yandex Business feed quality preview from supplied settings without
     * saving them or publishing the feed. Requires system-tenant Manager access via route policy;
     * reads the feed service's
     * canonical catalog scope. Returns the candidate settings with the quality report so it can be
     * compared before the owner-only update.
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
     * Download the canonical Yandex Business price list generated from current feed
     * settings/catalog data. Requires Manager access. Despite the .yml filename, the body is YML
     * XML with application/xml content type and attachment disposition, not YAML or JSON. This
     * read does not upload the feed to Yandex.
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
     * Read the quality report for the canonical Yandex Business feed using saved/effective feed
     * settings. Requires system-tenant Manager access via route policy; the report is not scoped
     * to an arbitrary caller-selected
     * storefront. Reports feed inclusion/exclusion diagnostics without updating products/settings
     * or submitting data to Yandex.
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
