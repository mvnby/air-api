/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerActionMessageResponse } from '../models/ManagerActionMessageResponse';
import type { ManagerBrandCreatePayload } from '../models/ManagerBrandCreatePayload';
import type { ManagerBrandListResponse } from '../models/ManagerBrandListResponse';
import type { ManagerBrandResponse } from '../models/ManagerBrandResponse';
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
}
