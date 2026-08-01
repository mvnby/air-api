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
