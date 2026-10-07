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
     * Query the shared catalog-management workspace using its combined technical, publication,
     * supplier and missing-data filters. Filtering precedes pagination. Supplier means a
     * mapped active supplier offer, not ownership of the product; results include draft and
     * orderable products.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [catalog
     * workspace](https://github.com/mvnby/air-api/blob/main/docs/catalog-management-workspace.md).
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
     * Resolve the same workspace filters to a bounded full selection of product IDs without
     * pagination. More than 500 matches returns 400 rather than a truncated selection. The
     * returned IDs are a snapshot; later preview/apply validates their current availability.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [catalog
     * workspace](https://github.com/mvnby/air-api/blob/main/docs/catalog-management-workspace.md).
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
     * Calculate before/after results for selected products inside a transaction that is rolled
     * back. No catalog changes are saved. Returns a signed token valid for 900 seconds, bound
     * to the tenant/storefront/actor, selection, change and product fingerprints. Invalid
     * choices return 400; unavailable products return 409. Apply must use this token.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [catalog
     * workspace](https://github.com/mvnby/air-api/blob/main/docs/catalog-management-workspace.md).
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
     * Apply the signed preview after locking selected products and checking their
     * fingerprints. All product changes commit in one transaction. Invalid/expired/wrong-actor
     * token returns 400; removed or changed products return 409 and require a new preview.
     * This is not a reusable idempotency receipt: a successful changing apply can make its own
     * preview stale.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [catalog
     * workspace](https://github.com/mvnby/air-api/blob/main/docs/catalog-management-workspace.md).
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
