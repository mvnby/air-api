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
import type { ManagerFeatureSuggestionsApplyPayload } from '../models/ManagerFeatureSuggestionsApplyPayload';
import type { ManagerProductFeaturesUpdatePayload } from '../models/ManagerProductFeaturesUpdatePayload';
import type { ManagerProductFeatureWorkspaceResponse } from '../models/ManagerProductFeatureWorkspaceResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerFeaturesService {
    /**
     * List Feature Categories
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
     * Get Feature
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
