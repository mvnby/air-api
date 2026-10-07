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
     * Read shared installation-discount policy and product overrides with current
     * margin/eligibility projections. page starts at 1 and limit is 1–100. The list covers
     * stored overrides rather than every catalog product, and does not change an accepted
     * estimate.
     *
     * Access and scope: system-tenant Manager access is required; these are shared platform
     * definitions. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
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
     * Search shared product candidates for discount overrides, returning current price/margin
     * eligibility and whether an override exists. q is at most 200 characters and limit is
     * 1–50. This only reads suggestions; it does not create rules or recalculate accepted
     * installation snapshots.
     *
     * Access and scope: system-tenant Manager access is required; these are shared platform
     * definitions. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
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
     * Save the shared enable flag, default installation discount and minimum margin policy.
     * The legacy installation-discount fallback is synchronized when toggling this policy.
     * This affects future pricing decisions, not tenant rate dictionaries or already accepted
     * estimates; a repeated PUT saves the submitted policy without an idempotency receipt.
     *
     * Access and scope: system-tenant Manager access is required; these are shared platform
     * definitions. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
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
     * Create or update the unique installation-discount override for one shared product,
     * returning its current economic decision after saving. Missing product returns 404.
     * Repeating the same product PUT reuses that override; existing accepted estimate
     * snapshots are not rewritten.
     *
     * Access and scope: system-tenant Manager access is required; these are shared platform
     * definitions. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
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
     * Permanently remove a product discount override and return 204 so future decisions use
     * the shared policy fallback. Missing override returns 404, including repeats. This does
     * not disable the global policy or change accepted estimates.
     *
     * Access and scope: system-tenant Manager access is required; these are shared platform
     * definitions. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
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
