/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TenderModuleAccess } from '../models/TenderModuleAccess';
import type { TenderModuleEntitlementUpdate } from '../models/TenderModuleEntitlementUpdate';
import type { TenderModuleSettings } from '../models/TenderModuleSettings';
import type { TenderModuleUpdate } from '../models/TenderModuleUpdate';
import type { TenderProfilePreview } from '../models/TenderProfilePreview';
import type { TenderSearchProfile } from '../models/TenderSearchProfile';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerTenderModuleService {
    /**
     * Get Manager Tender Module
     * Read module access, enablement, and the selected company's search profiles.
     * @returns TenderModuleSettings Successful Response
     * @throws ApiError
     */
    public static getManagerTenderModule(): CancelablePromise<TenderModuleSettings> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/tender-module',
        });
    }
    /**
     * Update Manager Tender Module
     * Save versioned preferences for the selected company with active module access.
     * @param requestBody
     * @returns TenderModuleSettings Successful Response
     * @throws ApiError
     */
    public static updateManagerTenderModule(
        requestBody: TenderModuleUpdate,
    ): CancelablePromise<TenderModuleSettings> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/tender-module',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Platform Company Tender Module
     * Read the specified company's entitlement as the platform owner.
     * @param tenantId
     * @returns TenderModuleAccess Successful Response
     * @throws ApiError
     */
    public static getPlatformCompanyTenderModule(
        tenantId: number,
    ): CancelablePromise<TenderModuleAccess> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/platform/companies/{tenant_id}/tender-module',
            path: {
                'tenant_id': tenantId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Platform Company Tender Module
     * Grant or revoke module access with a version check and an audit entry.
     * @param tenantId
     * @param requestBody
     * @returns TenderModuleAccess Successful Response
     * @throws ApiError
     */
    public static updatePlatformCompanyTenderModule(
        tenantId: number,
        requestBody: TenderModuleEntitlementUpdate,
    ): CancelablePromise<TenderModuleAccess> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/platform/companies/{tenant_id}/tender-module',
            path: {
                'tenant_id': tenantId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Preview Manager Tender Profile
     * Apply the draft filter to the most recent tenders in the selected storefront.
     * @param requestBody
     * @returns TenderProfilePreview Successful Response
     * @throws ApiError
     */
    public static previewManagerTenderProfile(
        requestBody: TenderSearchProfile,
    ): CancelablePromise<TenderProfilePreview> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/tender-module/profile-preview',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
