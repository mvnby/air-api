/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerProductCollectionCreate } from '../models/ManagerProductCollectionCreate';
import type { ManagerProductCollectionItemsPayload } from '../models/ManagerProductCollectionItemsPayload';
import type { ManagerProductCollectionListResponse } from '../models/ManagerProductCollectionListResponse';
import type { ManagerProductCollectionPlacementsPayload } from '../models/ManagerProductCollectionPlacementsPayload';
import type { ManagerProductCollectionProductOptionListResponse } from '../models/ManagerProductCollectionProductOptionListResponse';
import type { ManagerProductCollectionResponse } from '../models/ManagerProductCollectionResponse';
import type { ManagerProductCollectionUpdate } from '../models/ManagerProductCollectionUpdate';
import type { ManagerProductCollectionWorkspacePayload } from '../models/ManagerProductCollectionWorkspacePayload';
import type { ProductCollectionPreviewResponse } from '../models/ProductCollectionPreviewResponse';
import type { ProductCollectionRuleOptionsResponse } from '../models/ProductCollectionRuleOptionsResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerProductCollectionsService {
    /**
     * Search Manager Product Collection Products
     * Search products visible to this storefront for manual collection items. search is
     * required and limit is 1–100. Returned commercial data is current scoped projection;
     * results are not a certification that each product will pass the chosen placement’s
     * eligibility checks.
     *
     * Access and scope: Manager access and storefront.collections.manage capability are
     * required; collections belong to the authenticated tenant and selected storefront. See
     * [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [collection
     * contract](https://github.com/mvnby/air-api/blob/main/docs/product-collections.md).
     * @param search
     * @param limit
     * @returns ManagerProductCollectionProductOptionListResponse Successful Response
     * @throws ApiError
     */
    public static searchManagerProductCollectionProducts(
        search: string,
        limit: number = 30,
    ): CancelablePromise<ManagerProductCollectionProductOptionListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/product-collections/product-options',
            query: {
                'search': search,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Manager Product Collection Rule Options
     * Read brand, series and resolved-feature filter choices from products visible to the
     * selected storefront. This supplies typed rule options, not arbitrary expression
     * execution or internal supplier/stock ownership data.
     *
     * Access and scope: Manager access and storefront.collections.manage capability are
     * required; collections belong to the authenticated tenant and selected storefront. See
     * [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [collection
     * contract](https://github.com/mvnby/air-api/blob/main/docs/product-collections.md).
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
     * Read all collections for the selected storefront with their current metadata and child
     * records. No pagination parameters are accepted; draft/published/archived state is
     * represented in the response. This does not resolve public slot eligibility or publish a
     * collection.
     *
     * Access and scope: Manager access and storefront.collections.manage capability are
     * required; collections belong to the authenticated tenant and selected storefront. See
     * [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [collection
     * contract](https://github.com/mvnby/air-api/blob/main/docs/product-collections.md).
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
     * Create storefront collection metadata, normalizing its slug and validating
     * rules/fallback. Default status is draft, but supplied status is honored. Empty required
     * copy or incomplete automatic/hybrid rules returns 400; inaccessible fallback returns
     * 404; partner internal-stock filters return 403. This does not create items/placements
     * and has no idempotency receipt. Concurrent persistence conflicts return 409; reread
     * current state before retrying.
     *
     * Access and scope: Manager access and storefront.collections.manage capability are
     * required; collections belong to the authenticated tenant and selected storefront. See
     * [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [collection
     * contract](https://github.com/mvnby/air-api/blob/main/docs/product-collections.md).
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
     * Read a saved storefront collection and its items/placements. Missing or out-of-scope
     * collection returns 404. Product commercial data is resolved separately at preview/public
     * read time; this response describes editorial configuration.
     *
     * Access and scope: Manager access and storefront.collections.manage capability are
     * required; collections belong to the authenticated tenant and selected storefront. See
     * [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [collection
     * contract](https://github.com/mvnby/air-api/blob/main/docs/product-collections.md).
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
     * Update only submitted collection metadata/rules within the selected storefront.
     * Missing/out-of-scope collection or fallback returns 404; invalid combined
     * fields/self-fallback/rules returns 400; partner internal-stock rules return 403.
     * Items/placements are edited separately or with workspace. No expected_version is
     * accepted. Concurrent persistence conflicts return 409; reread current state before
     * retrying.
     *
     * Access and scope: Manager access and storefront.collections.manage capability are
     * required; collections belong to the authenticated tenant and selected storefront. See
     * [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [collection
     * contract](https://github.com/mvnby/air-api/blob/main/docs/product-collections.md).
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
     * Create a separate draft copy of collection metadata/rules and still-visible manual
     * items. Placements are not copied, so the copy does not claim the source slots;
     * hidden/unavailable source items are omitted. Missing/out-of-scope source returns 404.
     * Each successful POST creates a new collection and has no idempotency receipt. Concurrent
     * persistence conflicts return 409; reread current state before retrying.
     *
     * Access and scope: Manager access and storefront.collections.manage capability are
     * required; collections belong to the authenticated tenant and selected storefront. See
     * [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [collection
     * contract](https://github.com/mvnby/air-api/blob/main/docs/product-collections.md).
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
     * Set collection status to archived and record audit/invalidation, retaining its
     * items/placements. Missing/out-of-scope collection returns 404. This removes it from
     * public active resolution rather than physically deleting it; repeats can create another
     * audit update. Concurrent persistence conflicts return 409; reread current state before
     * retrying.
     *
     * Access and scope: Manager access and storefront.collections.manage capability are
     * required; collections belong to the authenticated tenant and selected storefront. See
     * [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [collection
     * contract](https://github.com/mvnby/air-api/blob/main/docs/product-collections.md).
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
     * Replace the entire ordered manual item list, retaining pin/editorial-note settings and
     * removing omitted entries. Missing/out-of-scope collection or unavailable products
     * returns 404; duplicate product IDs return 400. Parent collection is locked and
     * items/audit/invalidation commit together. Visibility checks do not guarantee placement
     * eligibility; no expected_version is accepted. Concurrent persistence conflicts return
     * 409; reread current state before retrying.
     *
     * Access and scope: Manager access and storefront.collections.manage capability are
     * required; collections belong to the authenticated tenant and selected storefront. See
     * [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [collection
     * contract](https://github.com/mvnby/air-api/blob/main/docs/product-collections.md).
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
     * Replace all placements for a collection, deleting omitted assignments and saving
     * per-slot display/schedule settings. Missing/out-of-scope collection returns 404;
     * duplicate surface/slot pairs or invalid keys returns 400. Parent collection is locked;
     * audit and invalidation commit with the replacement. Publishing still depends on
     * collection status, schedule and resolver eligibility. Concurrent persistence conflicts
     * return 409; reread current state before retrying.
     *
     * Access and scope: Manager access and storefront.collections.manage capability are
     * required; collections belong to the authenticated tenant and selected storefront. See
     * [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [collection
     * contract](https://github.com/mvnby/air-api/blob/main/docs/product-collections.md).
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
     * Resolve a saved collection for a requested surface/slot using current visible product
     * data, rule eligibility, minimum count, fallback and placement layout. Drafts can be
     * previewed without publishing. Daily rotation uses the UTC date; independent preview does
     * not guarantee this collection wins the public slot. Missing/out-of-scope collection
     * returns 404; no writes or draft edits are saved.
     *
     * Access and scope: Manager access and storefront.collections.manage capability are
     * required; collections belong to the authenticated tenant and selected storefront. See
     * [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [collection
     * contract](https://github.com/mvnby/air-api/blob/main/docs/product-collections.md).
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
    /**
     * Save Manager Product Collection Workspace
     * Atomically update collection fields and replace its full item/placement sets, with audit
     * and invalidation in one transaction. Parent lock serializes metadata and child edits;
     * any failure rolls everything back. Unknown/out-of-scope references return 404, invalid
     * duplicates/rules/fields 400, partner internal-stock rules 403. No expected_version is
     * accepted; this saves directly rather than creating an unpublished revision. Concurrent
     * persistence conflicts return 409; reread current state before retrying.
     *
     * Access and scope: Manager access and storefront.collections.manage capability are
     * required; collections belong to the authenticated tenant and selected storefront. See
     * [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [collection
     * contract](https://github.com/mvnby/air-api/blob/main/docs/product-collections.md).
     * @param collectionId
     * @param requestBody
     * @returns ManagerProductCollectionResponse Successful Response
     * @throws ApiError
     */
    public static saveManagerProductCollectionWorkspace(
        collectionId: number,
        requestBody: ManagerProductCollectionWorkspacePayload,
    ): CancelablePromise<ManagerProductCollectionResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/product-collections/{collection_id}/workspace',
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
}
