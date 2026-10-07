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
import type { ManagerSeriesGalleryApplyPayload } from '../models/ManagerSeriesGalleryApplyPayload';
import type { ManagerSeriesGalleryApplyResponse } from '../models/ManagerSeriesGalleryApplyResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerBrandsService {
    /**
     * List Manager Brands
     * List all brands with product counts, ordered by sort_order and title. No pagination
     * parameters are accepted.
     *
     * Access and scope: Manager access is required; this reads the shared platform catalog,
     * not tenant-owned copies. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Create a shared brand and synchronize its brand tag. Title and generated/requested slug
     * must be nonempty; an existing slug or invalid publication media returns 400. This POST
     * has no idempotency receipt.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
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
     * Update submitted brand fields and synchronize the brand tag when identity changes.
     * Missing brand returns 404; conflicting slug, empty title or invalid content media
     * returns 400. Semantic no-op edits do not publish a new catalog revision.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
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
     * Delete a brand and its unused brand tag. Missing brand returns 404, including after
     * prior deletion; products, series or products attached to its tag block deletion with
     * 400. This is a permanent delete, not hiding a brand.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * List active shared features belonging to one brand with series-assignment counts.
     * Missing brand returns 404; this list is not paginated. Creating a brand feature alone
     * does not assign it to all brand products.
     *
     * Access and scope: Manager access is required; this reads the shared platform catalog,
     * not tenant-owned copies. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [feature
     * taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
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
     * Create a brand-owned feature through the brand editor. Missing brand returns 404; empty
     * title, duplicate slug within the brand or invalid feature media returns 400. Creation
     * does not assign the feature to series/products and has no idempotency receipt.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [feature
     * taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
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
     * Update submitted fields of a feature belonging to the requested brand. Missing brand or
     * feature returns 404; empty title, duplicate brand slug or invalid media returns 400.
     * Assignments to series are preserved.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [feature
     * taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
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
     * Archive an unassigned brand feature by setting it inactive and preserving its
     * definition/history. Missing brand or feature returns 404; any series assignment blocks
     * archiving with 400. An already archived unassigned feature is a semantic no-op; this is
     * not a physical delete.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [feature
     * taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
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
     * List series belonging to a brand, including hidden series, product counts and feature
     * assignments. Missing brand returns 404; no page/limit parameters are accepted.
     *
     * Access and scope: Manager access is required; this reads the shared platform catalog,
     * not tenant-owned copies. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [feature
     * taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
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
     * Create a shared series under the requested brand, validating its feature assignments and
     * publication media. Missing brand returns 404; empty title, conflicting slug or invalid
     * feature/media choices returns 400. This POST has no idempotency receipt.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [feature
     * taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
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
     * Update submitted series fields and, when supplied, replace feature assignments. Missing
     * brand/series returns 404; invalid assignments/media, duplicate slug or including a
     * hidden series in the brand showcase returns 400. Feature priority permits at most three
     * featured entries.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [feature
     * taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
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
     * Permanently delete a series and its feature links. Missing brand/series returns 404;
     * assigned products block deletion with 400, so hide a used series instead. A repeat after
     * deletion returns 404.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
    /**
     * Apply Manager Series Gallery To Products
     * Save the submitted nonempty gallery on the series and add those URLs to every assigned
     * product. Existing links are skipped; product main images are not changed. Missing
     * brand/series returns 404; empty/invalid media returns 400. Series and product changes
     * commit together; this writes state rather than producing a preview.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
     * @param brandId
     * @param seriesId
     * @param requestBody
     * @returns ManagerSeriesGalleryApplyResponse Successful Response
     * @throws ApiError
     */
    public static applyManagerSeriesGalleryToProducts(
        brandId: number,
        seriesId: number,
        requestBody: ManagerSeriesGalleryApplyPayload,
    ): CancelablePromise<ManagerSeriesGalleryApplyResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/brands/{brand_id}/series/{series_id}/gallery/apply-to-products',
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
}
