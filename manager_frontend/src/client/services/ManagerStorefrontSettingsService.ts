/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_upload_manager_storefront_logo } from '../models/Body_upload_manager_storefront_logo';
import type { ManagerMediaAssetUploadResponse } from '../models/ManagerMediaAssetUploadResponse';
import type { StorefrontBrandResponse } from '../models/StorefrontBrandResponse';
import type { StorefrontSettingsPayload } from '../models/StorefrontSettingsPayload';
import type { StorefrontSettingsResponse } from '../models/StorefrontSettingsResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerStorefrontSettingsService {
    /**
     * Get Storefront Brand
     * @returns StorefrontBrandResponse Successful Response
     * @throws ApiError
     */
    public static getManagerStorefrontBrand(): CancelablePromise<StorefrontBrandResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/storefront-settings/brand',
        });
    }
    /**
     * Upload Storefront Logo
     * @param formData
     * @returns ManagerMediaAssetUploadResponse Successful Response
     * @throws ApiError
     */
    public static uploadManagerStorefrontLogo(
        formData: Body_upload_manager_storefront_logo,
    ): CancelablePromise<ManagerMediaAssetUploadResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/storefront-settings/logo',
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
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
