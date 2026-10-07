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
     * Add batched UI action counters to platform-wide daily aggregates in Europe/Minsk and
     * prune data older than the 90-day retention window. Payload contains action dimensions
     * rather than search/product/customer content. No idempotency receipt exists: replay
     * counts events again. Per-actor rate/concurrency limits may return 429 with Retry-After.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [catalog
     * workspace](https://github.com/mvnby/air-api/blob/main/docs/catalog-management-workspace.md).
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
     * Read platform-wide daily catalog-workspace telemetry over 1–90 days, optionally filtered
     * by layout, device, action or outcome. Dates use Europe/Minsk; the report is aggregate
     * counters, not individual users or recordings. Reading does not enable event collection.
     *
     * Access and scope: system-tenant Manager access and analytics.manage capability are
     * required; aggregates are platform-wide. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [catalog
     * workspace](https://github.com/mvnby/air-api/blob/main/docs/catalog-management-workspace.md).
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
