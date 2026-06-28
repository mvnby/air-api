/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerActionMessageResponse } from '../models/ManagerActionMessageResponse';
import type { ManagerBrandCreatePayload } from '../models/ManagerBrandCreatePayload';
import type { ManagerBrandFeatureCreatePayload } from '../models/ManagerBrandFeatureCreatePayload';
import type { ManagerBrandFeatureListResponse } from '../models/ManagerBrandFeatureListResponse';
import type { ManagerBrandFeatureResponse } from '../models/ManagerBrandFeatureResponse';
import type { ManagerBrandFeatureUpdatePayload } from '../models/ManagerBrandFeatureUpdatePayload';
import type { ManagerBrandListResponse } from '../models/ManagerBrandListResponse';
import type { ManagerBrandResponse } from '../models/ManagerBrandResponse';
import type { ManagerBrandSeriesCreatePayload } from '../models/ManagerBrandSeriesCreatePayload';
import type { ManagerBrandSeriesListResponse } from '../models/ManagerBrandSeriesListResponse';
import type { ManagerBrandSeriesResponse } from '../models/ManagerBrandSeriesResponse';
import type { ManagerBrandSeriesUpdatePayload } from '../models/ManagerBrandSeriesUpdatePayload';
import type { ManagerBrandUpdatePayload } from '../models/ManagerBrandUpdatePayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerBrandsService {
    /**
     * List Manager Brands
     * @returns ManagerBrandListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerBrands(): CancelablePromise<ManagerBrandListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/brands',
        });
    }
    /**
     * Create Manager Brand
     * @param requestBody
     * @returns ManagerBrandResponse Successful Response
     * @throws ApiError
     */
    public static createManagerBrand(
        requestBody: ManagerBrandCreatePayload,
    ): CancelablePromise<ManagerBrandResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/brands',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Manager Brand
     * @param brandId
     * @param requestBody
     * @returns ManagerBrandResponse Successful Response
     * @throws ApiError
     */
    public static updateManagerBrand(
        brandId: number,
        requestBody: ManagerBrandUpdatePayload,
    ): CancelablePromise<ManagerBrandResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/brands/{brand_id}',
            path: {
                'brand_id': brandId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Manager Brand
     * @param brandId
     * @returns ManagerActionMessageResponse Successful Response
     * @throws ApiError
     */
    public static deleteManagerBrand(
        brandId: number,
    ): CancelablePromise<ManagerActionMessageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/brands/{brand_id}',
            path: {
                'brand_id': brandId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Manager Brand Features
     * @param brandId
     * @returns ManagerBrandFeatureListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerBrandFeatures(
        brandId: number,
    ): CancelablePromise<ManagerBrandFeatureListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/brands/{brand_id}/features',
            path: {
                'brand_id': brandId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Manager Brand Feature
     * @param brandId
     * @param requestBody
     * @returns ManagerBrandFeatureResponse Successful Response
     * @throws ApiError
     */
    public static createManagerBrandFeature(
        brandId: number,
        requestBody: ManagerBrandFeatureCreatePayload,
    ): CancelablePromise<ManagerBrandFeatureResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/brands/{brand_id}/features',
            path: {
                'brand_id': brandId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Manager Brand Feature
     * @param brandId
     * @param featureId
     * @param requestBody
     * @returns ManagerBrandFeatureResponse Successful Response
     * @throws ApiError
     */
    public static updateManagerBrandFeature(
        brandId: number,
        featureId: number,
        requestBody: ManagerBrandFeatureUpdatePayload,
    ): CancelablePromise<ManagerBrandFeatureResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/brands/{brand_id}/features/{feature_id}',
            path: {
                'brand_id': brandId,
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
     * Delete Manager Brand Feature
     * @param brandId
     * @param featureId
     * @returns ManagerActionMessageResponse Successful Response
     * @throws ApiError
     */
    public static deleteManagerBrandFeature(
        brandId: number,
        featureId: number,
    ): CancelablePromise<ManagerActionMessageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/brands/{brand_id}/features/{feature_id}',
            path: {
                'brand_id': brandId,
                'feature_id': featureId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Manager Brand Series
     * @param brandId
     * @returns ManagerBrandSeriesListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerBrandSeries(
        brandId: number,
    ): CancelablePromise<ManagerBrandSeriesListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/brands/{brand_id}/series',
            path: {
                'brand_id': brandId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Manager Brand Series
     * @param brandId
     * @param requestBody
     * @returns ManagerBrandSeriesResponse Successful Response
     * @throws ApiError
     */
    public static createManagerBrandSeries(
        brandId: number,
        requestBody: ManagerBrandSeriesCreatePayload,
    ): CancelablePromise<ManagerBrandSeriesResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/brands/{brand_id}/series',
            path: {
                'brand_id': brandId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Manager Brand Series
     * @param brandId
     * @param seriesId
     * @param requestBody
     * @returns ManagerBrandSeriesResponse Successful Response
     * @throws ApiError
     */
    public static updateManagerBrandSeries(
        brandId: number,
        seriesId: number,
        requestBody: ManagerBrandSeriesUpdatePayload,
    ): CancelablePromise<ManagerBrandSeriesResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/brands/{brand_id}/series/{series_id}',
            path: {
                'brand_id': brandId,
                'series_id': seriesId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Manager Brand Series
     * @param brandId
     * @param seriesId
     * @returns ManagerActionMessageResponse Successful Response
     * @throws ApiError
     */
    public static deleteManagerBrandSeries(
        brandId: number,
        seriesId: number,
    ): CancelablePromise<ManagerActionMessageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/brands/{brand_id}/series/{series_id}',
            path: {
                'brand_id': brandId,
                'series_id': seriesId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
