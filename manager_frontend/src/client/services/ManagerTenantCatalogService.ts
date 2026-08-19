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
