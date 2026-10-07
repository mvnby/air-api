/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { FeatureCategoryResponse } from '../models/FeatureCategoryResponse';
import type { FeatureCreatePayload } from '../models/FeatureCreatePayload';
import type { FeatureTargetLinkPayload } from '../models/FeatureTargetLinkPayload';
import type { FeatureUpdatePayload } from '../models/FeatureUpdatePayload';
import type { ManagerFeatureListResponse } from '../models/ManagerFeatureListResponse';
import type { ManagerFeatureResponse } from '../models/ManagerFeatureResponse';
import type { ManagerFeatureSeriesMigrationApplyPayload } from '../models/ManagerFeatureSeriesMigrationApplyPayload';
import type { ManagerFeatureSeriesMigrationApplyResponse } from '../models/ManagerFeatureSeriesMigrationApplyResponse';
import type { ManagerFeatureSeriesMigrationPreviewResponse } from '../models/ManagerFeatureSeriesMigrationPreviewResponse';
import type { ManagerFeatureSuggestionsApplyPayload } from '../models/ManagerFeatureSuggestionsApplyPayload';
import type { ManagerProductFeaturesUpdatePayload } from '../models/ManagerProductFeaturesUpdatePayload';
import type { ManagerProductFeatureWorkspaceResponse } from '../models/ManagerProductFeatureWorkspaceResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerFeaturesService {
    /**
     * List Feature Categories
     * Read feature-library categories in their display order. This shared dictionary has no
     * pagination and reading it does not create or assign features.
     *
     * Access and scope: Manager access is required; this reads the shared platform catalog,
     * not tenant-owned copies. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [feature
     * taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
     * @returns FeatureCategoryResponse Successful Response
     * @throws ApiError
     */
    public static listManagerFeatureCategories(): CancelablePromise<Array<FeatureCategoryResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/feature-categories',
        });
    }
    /**
     * List Features
     * Read shared feature definitions with category/brand/product/scope filters. Active
     * features are shown by default; is_active may select archived definitions. product_id
     * checks product existence and returns 404 if missing. total is the returned list length;
     * no pagination is accepted.
     *
     * Access and scope: Manager access is required; this reads the shared platform catalog,
     * not tenant-owned copies. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [feature
     * taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
     * @param search
     * @param categoryId
     * @param brandId
     * @param productId
     * @param scopeType
     * @param isActive
     * @returns ManagerFeatureListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerFeatures(
        search?: (string | null),
        categoryId?: (number | null),
        brandId?: (number | null),
        productId?: (number | null),
        scopeType?: ('universal' | 'brand' | 'series' | 'product' | 'derived' | null),
        isActive?: (boolean | null),
    ): CancelablePromise<ManagerFeatureListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/features',
            query: {
                'search': search,
                'category_id': categoryId,
                'brand_id': brandId,
                'product_id': productId,
                'scope_type': scopeType,
                'is_active': isActive,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Feature
     * Create a feature and its automatic rules; is_active defaults to true. New definitions
     * support universal or brand ownership; brand features require a valid brand and only
     * universal features accept automatic rules. Invalid category, replacement, scope or
     * unpublished media returns 400. Returns 201; creation does not assign it to every brand
     * product and has no idempotency receipt.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [feature
     * taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
     * @param requestBody
     * @returns ManagerFeatureResponse Successful Response
     * @throws ApiError
     */
    public static createManagerFeature(
        requestBody: FeatureCreatePayload,
    ): CancelablePromise<ManagerFeatureResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/features',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Preview Feature Series Migration
     * Read candidates where the same active manual feature is assigned without individual
     * overrides to every published product in a series. Omitted/empty valid series IDs scans
     * all series; returned candidate tokens describe the current source links. This read-only
     * report does not create series links or remove product links.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [feature
     * taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
     * @param seriesIds
     * @returns ManagerFeatureSeriesMigrationPreviewResponse Successful Response
     * @throws ApiError
     */
    public static previewManagerFeatureSeriesMigration(
        seriesIds?: (Array<number> | null),
    ): CancelablePromise<ManagerFeatureSeriesMigrationPreviewResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/features/series-migration/preview',
            query: {
                'series_ids': seriesIds,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Apply Feature Series Migration
     * Move only submitted candidate rows from repeated product assignments to series
     * assignments, deleting the matching product links in one transaction. Duplicate
     * candidates return 400; stale tokens/source links or changed eligibility return 409. Rows
     * are locked and revalidated; refresh preview after conflict. This mutates catalog
     * inheritance and is not a background job.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [feature
     * taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
     * @param requestBody
     * @returns ManagerFeatureSeriesMigrationApplyResponse Successful Response
     * @throws ApiError
     */
    public static applyManagerFeatureSeriesMigration(
        requestBody: ManagerFeatureSeriesMigrationApplyPayload,
    ): CancelablePromise<ManagerFeatureSeriesMigrationApplyResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/features/series-migration/apply',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Feature
     * Read a shared feature definition, rules and relationships, including archived
     * definitions. Missing feature returns 404. Library ownership scope is distinct from
     * effective product visibility.
     *
     * Access and scope: Manager access is required; this reads the shared platform catalog,
     * not tenant-owned copies. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [feature
     * taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
     * @param featureId
     * @returns ManagerFeatureResponse Successful Response
     * @throws ApiError
     */
    public static getManagerFeature(
        featureId: number,
    ): CancelablePromise<ManagerFeatureResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/features/{feature_id}',
            path: {
                'feature_id': featureId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Feature
     * Update supplied definition fields/rules, validating ownership, replacements and media
     * readiness. Missing feature returns 404; invalid references, replacement cycles or
     * illegal scope changes returns 400. Legacy series/product/derived definitions must be
     * migrated to universal or brand before ordinary editing.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [feature
     * taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
     * @param featureId
     * @param requestBody
     * @returns ManagerFeatureResponse Successful Response
     * @throws ApiError
     */
    public static updateManagerFeature(
        featureId: number,
        requestBody: FeatureUpdatePayload,
    ): CancelablePromise<ManagerFeatureResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/features/{feature_id}',
            path: {
                'feature_id': featureId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Archive Feature
     * Set the feature inactive and return its archived definition; this is not a physical
     * delete. Missing feature returns 404. Archiving changes effective catalog projections
     * while keeping the stored definition and historical relationships.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [feature
     * taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
     * @param featureId
     * @returns ManagerFeatureResponse Successful Response
     * @throws ApiError
     */
    public static archiveManagerFeature(
        featureId: number,
    ): CancelablePromise<ManagerFeatureResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/features/{feature_id}',
            path: {
                'feature_id': featureId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Upsert Target Link
     * Create or update a brand/series feature assignment and overrides; returns 204. Feature
     * and target must exist and ownership must allow the target. Invalid scope/media or a
     * fourth featured series feature returns 400; missing target returns 404. is_featured
     * applies only to series; universal rules resolve separately from stored assignments.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [feature
     * taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
     * @param featureId
     * @param targetType
     * @param targetId
     * @param requestBody
     * @returns void
     * @throws ApiError
     */
    public static upsertManagerFeatureTargetLink(
        featureId: number,
        targetType: 'brand' | 'series',
        targetId: number,
        requestBody: FeatureTargetLinkPayload,
    ): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/features/{feature_id}/{target_type}/{target_id}',
            path: {
                'feature_id': featureId,
                'target_type': targetType,
                'target_id': targetId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Target Link
     * Remove a stored brand/series assignment and return 204. Missing series returns 404; an
     * absent brand or assignment is a no-op in the current service. Removal stops that
     * inheritance path but does not archive the feature or suppress other rule/product
     * assignments.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [feature
     * taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
     * @param featureId
     * @param targetType
     * @param targetId
     * @returns void
     * @throws ApiError
     */
    public static deleteManagerFeatureTargetLink(
        featureId: number,
        targetType: 'brand' | 'series',
        targetId: number,
    ): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/features/{feature_id}/{target_type}/{target_id}',
            path: {
                'feature_id': featureId,
                'target_type': targetType,
                'target_id': targetId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Product Features
     * Read a product feature workspace with explicit assignments, effective
     * inherited/rule-derived features and automatic suggestions. Missing product returns 404.
     * This is a resolved view of shared catalog features, not only a raw relation list.
     *
     * Access and scope: Manager access is required; this reads the shared platform catalog,
     * not tenant-owned copies. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [feature
     * taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
     * @param productId
     * @returns ManagerProductFeatureWorkspaceResponse Successful Response
     * @throws ApiError
     */
    public static getManagerProductFeatures(
        productId: number,
    ): CancelablePromise<ManagerProductFeatureWorkspaceResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/products/{product_id}/features',
            path: {
                'product_id': productId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Product Features
     * Replace a product’s explicit feature assignments, including enabled/hidden overrides,
     * then return the resolved workspace. Omitted entries lose their explicit assignment;
     * inherited/rule-derived features may remain. Missing product returns 404; duplicate,
     * invalid, archived or incompatible features/media returns 400. Writes commit together.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [feature
     * taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
     * @param productId
     * @param requestBody
     * @returns ManagerProductFeatureWorkspaceResponse Successful Response
     * @throws ApiError
     */
    public static updateManagerProductFeatures(
        productId: number,
        requestBody: ManagerProductFeaturesUpdatePayload,
    ): CancelablePromise<ManagerProductFeatureWorkspaceResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/products/{product_id}/features',
            path: {
                'product_id': productId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Product Feature
     * Delete the explicit product assignment and return the resolved workspace. Missing
     * product returns 404; missing assignment is a no-op. Inherited or automatic features can
     * reappear, so deletion is different from an explicit hidden override.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [feature
     * taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
     * @param productId
     * @param featureId
     * @returns ManagerProductFeatureWorkspaceResponse Successful Response
     * @throws ApiError
     */
    public static deleteManagerProductFeature(
        productId: number,
        featureId: number,
    ): CancelablePromise<ManagerProductFeatureWorkspaceResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/products/{product_id}/features/{feature_id}',
            path: {
                'product_id': productId,
                'feature_id': featureId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Apply Product Feature Suggestions
     * Revalidate requested suggestion IDs and persist only legacy derived suggestions, then
     * return the resolved workspace. Universal automatic rules already resolve without stored
     * links. Missing product returns 404; outdated/unavailable suggestions return 409. Refresh
     * the workspace before retrying stale suggestions.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [feature
     * taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
     * @param productId
     * @param requestBody
     * @returns ManagerProductFeatureWorkspaceResponse Successful Response
     * @throws ApiError
     */
    public static applyManagerProductFeatureSuggestions(
        productId: number,
        requestBody: ManagerFeatureSuggestionsApplyPayload,
    ): CancelablePromise<ManagerProductFeatureWorkspaceResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/products/{product_id}/features/suggestions/apply',
            path: {
                'product_id': productId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
