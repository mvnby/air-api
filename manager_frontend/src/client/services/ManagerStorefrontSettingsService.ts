/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { StorefrontSettingsPayload } from '../models/StorefrontSettingsPayload';
import type { StorefrontSettingsResponse } from '../models/StorefrontSettingsResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerStorefrontSettingsService {
    /**
     * Get Storefront Settings
     * @returns StorefrontSettingsResponse Successful Response
     * @throws ApiError
     */
    public static getManagerStorefrontSettings(): CancelablePromise<StorefrontSettingsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/storefront-settings',
        });
    }
    /**
     * Update Storefront Settings
     * @param requestBody
     * @returns StorefrontSettingsResponse Successful Response
     * @throws ApiError
     */
    public static updateManagerStorefrontSettings(
        requestBody: StorefrontSettingsPayload,
    ): CancelablePromise<StorefrontSettingsResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/storefront-settings',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
