/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerTenantAuditEventListResponse } from '../models/ManagerTenantAuditEventListResponse';
import type { ManagerTenantOfferListResponse } from '../models/ManagerTenantOfferListResponse';
import type { ManagerTenantOfferResponse } from '../models/ManagerTenantOfferResponse';
import type { ManagerTenantOfferUpdate } from '../models/ManagerTenantOfferUpdate';
import type { ManagerTenantOfferUpsert } from '../models/ManagerTenantOfferUpsert';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerTenantOffersService {
    /**
     * List Manager Tenant Audit Events
     * Read scoped commercial-change audit events, including actor and change set, using offset
     * and limit (1–100). It only exposes events for the authenticated tenant/selected
     * storefront; reading does not acknowledge or remove them.
     *
     * Access and scope: Manager access is required; data is restricted to the authenticated
     * tenant and selected storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param offset
     * @param limit
     * @returns ManagerTenantAuditEventListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerTenantAuditEvents(
        offset?: number,
        limit: number = 50,
    ): CancelablePromise<ManagerTenantAuditEventListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/tenant-offers/audit',
            query: {
                'offset': offset,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Manager Tenant Offers
     * Read offers only from the authenticated tenant/selected storefront, using offset and
     * limit (1–100). The list contains the storefront’s own commercial/publication fields; it
     * is not the master product editor or a supplier-offer feed.
     *
     * Access and scope: Manager access is required; data is restricted to the authenticated
     * tenant and selected storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param offset
     * @param limit
     * @returns ManagerTenantOfferListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerTenantOffers(
        offset?: number,
        limit: number = 50,
    ): CancelablePromise<ManagerTenantOfferListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/tenant-offers',
            query: {
                'offset': offset,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Upsert Manager Tenant Offer
     * Create or update the selected storefront offer for a product and stage its
     * audit/invalidation together. Missing storefront/product returns 404; inconsistent price
     * fields return 422; conflicting concurrent persistence returns 409. The product/scope
     * identify the upsert; this accepts no client idempotency receipt. Shared catalog fields
     * are not edited.
     *
     * Access and scope: system-tenant Manager access is required by the route policy; the
     * offer and audit remain restricted to the authenticated tenant and selected storefront.
     * See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param requestBody
     * @returns ManagerTenantOfferResponse Successful Response
     * @throws ApiError
     */
    public static upsertManagerTenantOffer(
        requestBody: ManagerTenantOfferUpsert,
    ): CancelablePromise<ManagerTenantOfferResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/tenant-offers',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Manager Tenant Offer
     * Read one offer within the authenticated tenant/selected storefront. Unknown or
     * out-of-scope offer returns 404; missing underlying product also returns 404. Knowing an
     * offer ID does not grant cross-storefront access.
     *
     * Access and scope: Manager access is required; data is restricted to the authenticated
     * tenant and selected storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param offerId
     * @returns ManagerTenantOfferResponse Successful Response
     * @throws ApiError
     */
    public static getManagerTenantOffer(
        offerId: number,
    ): CancelablePromise<ManagerTenantOfferResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/tenant-offers/{offer_id}',
            path: {
                'offer_id': offerId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Manager Tenant Offer
     * Update only submitted scoped offer fields and record audit/invalidation when values
     * change. Unknown or out-of-scope offer returns 404; invalid prices return 422; concurrent
     * persistence conflict returns 409. No expected_version or idempotency receipt is
     * accepted; reread current offer before resolving conflicting edits.
     *
     * Access and scope: system-tenant Manager access is required by the route policy; the
     * offer and audit remain restricted to the authenticated tenant and selected storefront.
     * See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param offerId
     * @param requestBody
     * @returns ManagerTenantOfferResponse Successful Response
     * @throws ApiError
     */
    public static updateManagerTenantOffer(
        offerId: number,
        requestBody: ManagerTenantOfferUpdate,
    ): CancelablePromise<ManagerTenantOfferResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/tenant-offers/{offer_id}',
            path: {
                'offer_id': offerId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
