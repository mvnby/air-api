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
     * Read settings for the storefront selected by public tenant resolution, including its
     * configured service availability.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
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
