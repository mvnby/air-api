/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AddressSuggestResponse } from '../models/AddressSuggestResponse';
import type { FxRateResponse } from '../models/FxRateResponse';
import type { ManagerSettingCreatePayload } from '../models/ManagerSettingCreatePayload';
import type { ManagerSettingListResponse } from '../models/ManagerSettingListResponse';
import type { ManagerSettingResponse } from '../models/ManagerSettingResponse';
import type { ManagerSettingUpdatePayload } from '../models/ManagerSettingUpdatePayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerSettingsService {
    /**
     * List Manager Settings
     * Read global platform configuration keys, stored values and descriptions, ordered by key.
     * Requires an owner/admin in the system tenant. These are platform-wide GlobalConfig values,
     * not current-storefront settings, and the response is not a generic secret-masking interface.
     * For storefront configuration use /api/manager/storefront-settings.
     * @returns ManagerSettingListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerSettings(): CancelablePromise<ManagerSettingListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/settings',
        });
    }
    /**
     * Create Manager Setting
     * Create a global platform configuration key/value and optional description. Requires a
     * system-tenant owner/admin. Existing keys return 400 rather than being overwritten, including
     * a repeated successful request. Commits immediately; this is not tenant/storefront
     * configuration and has no command replay receipt.
     * @param requestBody
     * @returns ManagerSettingResponse Successful Response
     * @throws ApiError
     */
    public static createManagerSetting(
        requestBody: ManagerSettingCreatePayload,
    ): CancelablePromise<ManagerSettingResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/settings',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Fx Rate
     * Read effective platform USD/BYN and EUR/BYN rates for an authenticated Manager. In manual
     * mode only USD has a manual value; EUR is null. In automatic mode rates come from the NBRB
     * provider cache/request, with manual USD fallback if unavailable. The source field records
     * the configured mode, not proof that a particular returned rate came from that provider.
     * Unavailable rates are null; this route does not save a rate.
     * @returns FxRateResponse Successful Response
     * @throws ApiError
     */
    public static getFxRate(): CancelablePromise<FxRateResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/settings/fx-rate',
        });
    }
    /**
     * Suggest Address
     * Query the external address-suggestion provider for an authenticated Manager without saving
     * an address. q requires at least two characters; geographic bias is sent only when both lat
     * and lon are present. Invalid parameters return 422, a service configuration/runtime error
     * returns 500, and upstream HTTP failure returns 502. Suggestions are provider results, not a
     * verified customer address.
     * @param q
     * @param lat
     * @param lon
     * @returns AddressSuggestResponse Successful Response
     * @throws ApiError
     */
    public static suggestAddress(
        q: string,
        lat?: (number | null),
        lon?: (number | null),
    ): CancelablePromise<AddressSuggestResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/settings/address-suggest',
            query: {
                'q': q,
                'lat': lat,
                'lon': lon,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Manager Setting
     * Replace the value of an existing global platform configuration key; update its description
     * only when provided. Requires a system-tenant owner/admin. Missing keys return 404; use POST
     * to create them. Commits immediately and updates the timestamp, without optimistic version
     * checks or an Idempotency-Key receipt. This does not update tenant storefront settings.
     * @param key
     * @param requestBody
     * @returns ManagerSettingResponse Successful Response
     * @throws ApiError
     */
    public static updateManagerSetting(
        key: string,
        requestBody: ManagerSettingUpdatePayload,
    ): CancelablePromise<ManagerSettingResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/settings/{key}',
            path: {
                'key': key,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
