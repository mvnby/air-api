/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerTenantCatalogListResponse } from '../models/ManagerTenantCatalogListResponse';
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
}
