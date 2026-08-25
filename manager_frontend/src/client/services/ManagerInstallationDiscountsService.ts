/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerInstallationDiscountPolicyResponse } from '../models/ManagerInstallationDiscountPolicyResponse';
import type { ManagerInstallationDiscountPolicyUpdatePayload } from '../models/ManagerInstallationDiscountPolicyUpdatePayload';
import type { ManagerInstallationDiscountProductResponse } from '../models/ManagerInstallationDiscountProductResponse';
import type { ManagerInstallationDiscountProductSearchResponse } from '../models/ManagerInstallationDiscountProductSearchResponse';
import type { ManagerInstallationDiscountRuleListResponse } from '../models/ManagerInstallationDiscountRuleListResponse';
import type { ManagerInstallationDiscountRuleUpdatePayload } from '../models/ManagerInstallationDiscountRuleUpdatePayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerInstallationDiscountsService {
    /**
     * List Manager Installation Discount Rules
     * @param search
     * @param page
     * @param limit
     * @returns ManagerInstallationDiscountRuleListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerInstallationDiscountRules(
        search?: (string | null),
        page: number = 1,
        limit: number = 50,
    ): CancelablePromise<ManagerInstallationDiscountRuleListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/installation-discounts',
            query: {
                'search': search,
                'page': page,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Search Manager Installation Discount Products
     * @param q
     * @param limit
     * @returns ManagerInstallationDiscountProductSearchResponse Successful Response
     * @throws ApiError
     */
    public static searchManagerInstallationDiscountProducts(
        q: string = '',
        limit: number = 20,
    ): CancelablePromise<ManagerInstallationDiscountProductSearchResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/installation-discounts/products/search',
            query: {
                'q': q,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Manager Installation Discount Policy
     * @param requestBody
     * @returns ManagerInstallationDiscountPolicyResponse Successful Response
     * @throws ApiError
     */
    public static updateManagerInstallationDiscountPolicy(
        requestBody: ManagerInstallationDiscountPolicyUpdatePayload,
    ): CancelablePromise<ManagerInstallationDiscountPolicyResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/installation-discounts/policy',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Upsert Manager Installation Discount Rule
     * @param productId
     * @param requestBody
     * @returns ManagerInstallationDiscountProductResponse Successful Response
     * @throws ApiError
     */
    public static upsertManagerInstallationDiscountRule(
        productId: number,
        requestBody: ManagerInstallationDiscountRuleUpdatePayload,
    ): CancelablePromise<ManagerInstallationDiscountProductResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/installation-discounts/products/{product_id}',
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
     * Delete Manager Installation Discount Rule
     * @param productId
     * @returns void
     * @throws ApiError
     */
    public static deleteManagerInstallationDiscountRule(
        productId: number,
    ): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/installation-discounts/products/{product_id}',
            path: {
                'product_id': productId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
