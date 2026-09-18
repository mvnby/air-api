/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CatalogUsageAccepted } from '../models/CatalogUsageAccepted';
import type { CatalogUsageBatch } from '../models/CatalogUsageBatch';
import type { CatalogUsageReport } from '../models/CatalogUsageReport';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerCatalogUsageService {
    /**
     * Record Manager Catalog Usage
     * @param requestBody
     * @returns CatalogUsageAccepted Successful Response
     * @throws ApiError
     */
    public static recordManagerCatalogUsage(
        requestBody: CatalogUsageBatch,
    ): CancelablePromise<CatalogUsageAccepted> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/catalog-usage/batch',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Manager Catalog Usage
     * @param days
     * @param layoutVersion
     * @param device
     * @param action
     * @param outcome
     * @returns CatalogUsageReport Successful Response
     * @throws ApiError
     */
    public static getManagerCatalogUsage(
        days: number = 30,
        layoutVersion?: (string | null),
        device?: ('mobile' | 'tablet' | 'desktop' | null),
        action?: ('product_open' | 'filter_apply' | 'filter_zero_results' | 'edit_basics' | 'edit_pricing' | 'edit_specifications' | 'edit_gallery' | 'edit_features' | 'bulk_edit' | 'gallery_quick_exit' | 'media_load' | null),
        outcome?: ('success' | 'cancelled' | 'failed' | 'zero_results' | 'quick_exit' | null),
    ): CancelablePromise<CatalogUsageReport> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/catalog-usage/daily',
            query: {
                'days': days,
                'layout_version': layoutVersion,
                'device': device,
                'action': action,
                'outcome': outcome,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
