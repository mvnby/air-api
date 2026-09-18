/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CatalogBulkApplyRequest } from '../models/CatalogBulkApplyRequest';
import type { CatalogBulkApplyResponse } from '../models/CatalogBulkApplyResponse';
import type { CatalogBulkPreviewRequest } from '../models/CatalogBulkPreviewRequest';
import type { CatalogBulkPreviewResponse } from '../models/CatalogBulkPreviewResponse';
import type { CatalogManagementFilters } from '../models/CatalogManagementFilters';
import type { CatalogManagementQuery } from '../models/CatalogManagementQuery';
import type { CatalogManagementSelection } from '../models/CatalogManagementSelection';
import type { ManagerCatalogProductListResponse } from '../models/ManagerCatalogProductListResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerCatalogManagementService {
    /**
     * Query Catalog
     * @param requestBody
     * @returns ManagerCatalogProductListResponse Successful Response
     * @throws ApiError
     */
    public static queryManagerCatalog(
        requestBody: CatalogManagementQuery,
    ): CancelablePromise<ManagerCatalogProductListResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/catalog-management/query',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Select Catalog
     * @param requestBody
     * @returns CatalogManagementSelection Successful Response
     * @throws ApiError
     */
    public static selectManagerCatalog(
        requestBody: CatalogManagementFilters,
    ): CancelablePromise<CatalogManagementSelection> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/catalog-management/selection',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Preview Bulk
     * @param requestBody
     * @returns CatalogBulkPreviewResponse Successful Response
     * @throws ApiError
     */
    public static previewManagerCatalogBulk(
        requestBody: CatalogBulkPreviewRequest,
    ): CancelablePromise<CatalogBulkPreviewResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/catalog-management/bulk/preview',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Apply Bulk
     * @param requestBody
     * @returns CatalogBulkApplyResponse Successful Response
     * @throws ApiError
     */
    public static applyManagerCatalogBulk(
        requestBody: CatalogBulkApplyRequest,
    ): CancelablePromise<CatalogBulkApplyResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/catalog-management/bulk/apply',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
