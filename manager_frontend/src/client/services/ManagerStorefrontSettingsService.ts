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
     * Read display name and ready logo URLs for the authenticated Manager's current storefront.
     * Available to Manager roles without owner-only settings access. An unconfigured storefront
     * uses service defaults; missing storefront returns 404. This projection excludes the rest of
     * the storefront settings.
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
     * Upload a storefront_logo media asset for the current storefront; requires a current-tenant
     * owner/admin. Accepts one multipart file up to 20 MiB; invalid media/size returns 400.
     * Returns uploaded asset metadata, but does not select it as the storefront logo: save its ID
     * through PUT /api/manager/storefront-settings. The upload may create assets/files and has no
     * command replay receipt.
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
     * Read site branding, contacts, service directions and optimistic version for the current
     * storefront; requires a current-tenant owner/admin. If no saved settings exist, returns
     * defaults with version=0 without creating a settings row; canonical system-storefront
     * defaults can include platform contacts. Missing storefront returns 404. Logo URLs refer only
     * to ready assets in this storefront.
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
     * Replace current-storefront site settings and service directions using the version returned
     * by GET. Requires a current-tenant owner/admin. Stale version returns 409; a logo must be a
     * ready storefront_logo asset of this storefront or returns 422; missing storefront returns
     * 404. A change increments version, records an audit event and stages catalog invalidation for
     * configured targets. Identical saved data with the current version is a no-op; retrying an
     * old version after a successful change conflicts.
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
