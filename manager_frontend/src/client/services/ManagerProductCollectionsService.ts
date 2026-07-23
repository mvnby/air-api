/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerProductCollectionCreate } from '../models/ManagerProductCollectionCreate';
import type { ManagerProductCollectionItemsPayload } from '../models/ManagerProductCollectionItemsPayload';
import type { ManagerProductCollectionListResponse } from '../models/ManagerProductCollectionListResponse';
import type { ManagerProductCollectionPlacementsPayload } from '../models/ManagerProductCollectionPlacementsPayload';
import type { ManagerProductCollectionResponse } from '../models/ManagerProductCollectionResponse';
import type { ManagerProductCollectionUpdate } from '../models/ManagerProductCollectionUpdate';
import type { ProductCollectionPreviewResponse } from '../models/ProductCollectionPreviewResponse';
import type { ProductCollectionRuleOptionsResponse } from '../models/ProductCollectionRuleOptionsResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerProductCollectionsService {
    /**
     * Get Manager Product Collection Rule Options
     * @returns ProductCollectionRuleOptionsResponse Successful Response
     * @throws ApiError
     */
    public static getManagerProductCollectionRuleOptions(): CancelablePromise<ProductCollectionRuleOptionsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/product-collections/rule-options',
        });
    }
    /**
     * List Manager Product Collections
     * @returns ManagerProductCollectionListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerProductCollections(): CancelablePromise<ManagerProductCollectionListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/product-collections',
        });
    }
    /**
     * Create Manager Product Collection
     * @param requestBody
     * @returns ManagerProductCollectionResponse Successful Response
     * @throws ApiError
     */
    public static createManagerProductCollection(
        requestBody: ManagerProductCollectionCreate,
    ): CancelablePromise<ManagerProductCollectionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/product-collections',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Manager Product Collection
     * @param collectionId
     * @returns ManagerProductCollectionResponse Successful Response
     * @throws ApiError
     */
    public static getManagerProductCollection(
        collectionId: number,
    ): CancelablePromise<ManagerProductCollectionResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/product-collections/{collection_id}',
            path: {
                'collection_id': collectionId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Manager Product Collection
     * @param collectionId
     * @param requestBody
     * @returns ManagerProductCollectionResponse Successful Response
     * @throws ApiError
     */
    public static updateManagerProductCollection(
        collectionId: number,
        requestBody: ManagerProductCollectionUpdate,
    ): CancelablePromise<ManagerProductCollectionResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/product-collections/{collection_id}',
            path: {
                'collection_id': collectionId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Duplicate Manager Product Collection
     * @param collectionId
     * @returns ManagerProductCollectionResponse Successful Response
     * @throws ApiError
     */
    public static duplicateManagerProductCollection(
        collectionId: number,
    ): CancelablePromise<ManagerProductCollectionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/product-collections/{collection_id}/duplicate',
            path: {
                'collection_id': collectionId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Archive Manager Product Collection
     * @param collectionId
     * @returns ManagerProductCollectionResponse Successful Response
     * @throws ApiError
     */
    public static archiveManagerProductCollection(
        collectionId: number,
    ): CancelablePromise<ManagerProductCollectionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/product-collections/{collection_id}/archive',
            path: {
                'collection_id': collectionId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Replace Manager Product Collection Items
     * @param collectionId
     * @param requestBody
     * @returns ManagerProductCollectionResponse Successful Response
     * @throws ApiError
     */
    public static replaceManagerProductCollectionItems(
        collectionId: number,
        requestBody: ManagerProductCollectionItemsPayload,
    ): CancelablePromise<ManagerProductCollectionResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/product-collections/{collection_id}/items',
            path: {
                'collection_id': collectionId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Replace Manager Product Collection Placements
     * @param collectionId
     * @param requestBody
     * @returns ManagerProductCollectionResponse Successful Response
     * @throws ApiError
     */
    public static replaceManagerProductCollectionPlacements(
        collectionId: number,
        requestBody: ManagerProductCollectionPlacementsPayload,
    ): CancelablePromise<ManagerProductCollectionResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/product-collections/{collection_id}/placements',
            path: {
                'collection_id': collectionId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Preview Manager Product Collection
     * @param collectionId
     * @param surface
     * @param slot
     * @returns ProductCollectionPreviewResponse Successful Response
     * @throws ApiError
     */
    public static previewManagerProductCollection(
        collectionId: number,
        surface: string = 'home',
        slot: string = 'featured_products',
    ): CancelablePromise<ProductCollectionPreviewResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/product-collections/{collection_id}/preview',
            path: {
                'collection_id': collectionId,
            },
            query: {
                'surface': surface,
                'slot': slot,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
