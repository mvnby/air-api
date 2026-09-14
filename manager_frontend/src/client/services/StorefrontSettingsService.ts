/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { StorefrontSettingsResponse } from '../models/StorefrontSettingsResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class StorefrontSettingsService {
    /**
     * Get Public Storefront Settings
     * @returns StorefrontSettingsResponse Successful Response
     * @throws ApiError
     */
    public static getPublicStorefrontSettings(): CancelablePromise<StorefrontSettingsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/storefront-settings',
        });
    }
}
