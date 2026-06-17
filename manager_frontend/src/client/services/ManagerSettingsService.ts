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
     * @param q
     * @returns AddressSuggestResponse Successful Response
     * @throws ApiError
     */
    public static suggestAddress(
        q: string,
    ): CancelablePromise<AddressSuggestResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/settings/address-suggest',
            query: {
                'q': q,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Manager Setting
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
