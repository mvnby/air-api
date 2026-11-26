/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TenderMarketEvidenceResult } from '../models/TenderMarketEvidenceResult';
import type { TenderMarketResults } from '../models/TenderMarketResults';
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
     * List Manager Tender Market
     * Read public results selected by the active company's saved profiles.
     *
     * Company entitlement and enablement are required. The response carries the
     * rules version and a cursor for the next bounded candidate scan. A profile
     * change returns 409 for a stale cursor. Reading does not create CRM records.
     * @param desired
     * @param profile
     * @param beforeId
     * @param settingsVersion
     * @param limit
     * @returns TenderMarketResults Successful Response
     * @throws ApiError
     */
    public static listManagerTenderMarket(
        desired: 'match' | 'review' = 'match',
        profile?: (string | null),
        beforeId?: (number | null),
        settingsVersion?: (number | null),
        limit: number = 30,
    ): CancelablePromise<TenderMarketResults> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/tender-market',
            query: {
                'desired': desired,
                'profile': profile,
                'before_id': beforeId,
                'settings_version': settingsVersion,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Manager Tender Market Evidence
     * Read the public original verification receipt for a publication visible to the active company.
     * @param publicationId
     * @returns TenderMarketEvidenceResult Successful Response
     * @throws ApiError
     */
    public static getManagerTenderMarketEvidence(
        publicationId: number,
    ): CancelablePromise<TenderMarketEvidenceResult> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/tender-market/{publication_id}/evidence',
            path: {
                'publication_id': publicationId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Request Manager Tender Market Evidence
     * Start or reuse a bounded original verification for a publication visible to the active company.
     * @param publicationId
     * @returns TenderMarketEvidenceResult Successful Response
     * @throws ApiError
     */
    public static requestManagerTenderMarketEvidence(
        publicationId: number,
    ): CancelablePromise<TenderMarketEvidenceResult> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/tender-market/{publication_id}/evidence',
            path: {
                'publication_id': publicationId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
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
