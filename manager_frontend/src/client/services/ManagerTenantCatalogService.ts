/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerTenantCatalogListResponse } from '../models/ManagerTenantCatalogListResponse';
import type { ManagerTenantCatalogProductDetailResponse } from '../models/ManagerTenantCatalogProductDetailResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerTenantCatalogService {
    /**
     * List Manager Tenant Catalog Products
     * Read published master products with the selected storefront’s offer projection,
     * paginated with limit 1–100. For partners, allowed means an active published offer whose
     * grant is active or absent; an inactive linked grant hides that offer from the
     * projection. For the system tenant allowed follows master publication and the allowed
     * filter is ignored. No grant or offer is created.
     *
     * Access and scope: Manager access is required; data is restricted to the authenticated
     * tenant and selected storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param page
     * @param limit
     * @param search
     * @param allowed
     * @returns ManagerTenantCatalogListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerTenantCatalogProducts(
        page: number = 1,
        limit: number = 40,
        search?: (string | null),
        allowed?: (boolean | null),
    ): CancelablePromise<ManagerTenantCatalogListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/tenant-catalog/products',
            query: {
                'page': page,
                'limit': limit,
                'search': search,
                'allowed': allowed,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Manager Tenant Catalog Product
     * Read one product's plain-text description, public gallery, manuals and complete
     * technical specifications. Requires Manager access and catalog.master.read capability.
     * Partners can browse published master content; allowed and effective_price use only
     * the authenticated tenant's selected storefront and valid offer/grant. System staff
     * may also read unpublished master content. Missing or unpublished partner products
     * return 404; invalid IDs return 422 and missing capability returns 403.
     *
     * selection_item is the current eligible published complete-split decision projection,
     * including its existing demo cost masking. Other products return null. No grants,
     * offers, selection or product data are created; GET is safe to repeat, including in
     * read-only demo accounts. Source provenance, raw supplier records and credentials
     * are excluded from the content projection.
     *
     * Access and scope: authenticated tenant and selected storefront; see [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param productId
     * @returns ManagerTenantCatalogProductDetailResponse Successful Response
     * @throws ApiError
     */
    public static getManagerTenantCatalogProduct(
        productId: number,
    ): CancelablePromise<ManagerTenantCatalogProductDetailResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/tenant-catalog/products/{product_id}',
            path: {
                'product_id': productId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
