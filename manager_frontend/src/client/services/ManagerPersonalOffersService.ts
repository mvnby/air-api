/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerPersonalOfferListResponse } from '../models/ManagerPersonalOfferListResponse';
import type { ManagerPersonalOfferResponse } from '../models/ManagerPersonalOfferResponse';
import type { PersonalOfferDraftInput } from '../models/PersonalOfferDraftInput';
import type { PersonalOfferPublishInput } from '../models/PersonalOfferPublishInput';
import type { PersonalOfferUpdateInput } from '../models/PersonalOfferUpdateInput';
import type { PersonalOfferVersionInput } from '../models/PersonalOfferVersionInput';
import type { PublicPersonalOfferResponse } from '../models/PublicPersonalOfferResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerPersonalOffersService {
    /**
     * List Manager Personal Offers
     * List drafts newest-first in the selected storefront, optionally for a CRM order.
     * @param orderId
     * @param limit
     * @param beforeId
     * @returns ManagerPersonalOfferListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerPersonalOffers(
        orderId?: (number | null),
        limit: number = 20,
        beforeId?: (number | null),
    ): CancelablePromise<ManagerPersonalOfferListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/personal-offers',
            query: {
                'order_id': orderId,
                'limit': limit,
                'before_id': beforeId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Manager Personal Offer
     * Save an unpublished draft, optionally tied to an in-scope order in negotiation.
     * @param requestBody
     * @returns ManagerPersonalOfferResponse Successful Response
     * @throws ApiError
     */
    public static createManagerPersonalOffer(
        requestBody: PersonalOfferDraftInput,
    ): CancelablePromise<ManagerPersonalOfferResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/personal-offers',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Manager Personal Offer
     * Read a draft and its current share link, if any.
     * @param offerId
     * @returns ManagerPersonalOfferResponse Successful Response
     * @throws ApiError
     */
    public static getManagerPersonalOffer(
        offerId: number,
    ): CancelablePromise<ManagerPersonalOfferResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/personal-offers/{offer_id}',
            path: {
                'offer_id': offerId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Manager Personal Offer
     * Replace editable draft fields using the last-read version. The live link is untouched.
     * @param offerId
     * @param requestBody
     * @returns ManagerPersonalOfferResponse Successful Response
     * @throws ApiError
     */
    public static updateManagerPersonalOffer(
        offerId: number,
        requestBody: PersonalOfferUpdateInput,
    ): CancelablePromise<ManagerPersonalOfferResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/personal-offers/{offer_id}',
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
    /**
     * Preview Manager Personal Offer
     * Render the saved draft using the same allowlist as the client-facing page.
     * @param offerId
     * @returns PublicPersonalOfferResponse Successful Response
     * @throws ApiError
     */
    public static previewManagerPersonalOffer(
        offerId: number,
    ): CancelablePromise<PublicPersonalOfferResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/personal-offers/{offer_id}/preview',
            path: {
                'offer_id': offerId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Publish Manager Personal Offer
     * Publish a fixed snapshot. Replay the same UUID and version to recover from a lost response.
     * @param offerId
     * @param requestBody
     * @returns ManagerPersonalOfferResponse Successful Response
     * @throws ApiError
     */
    public static publishManagerPersonalOffer(
        offerId: number,
        requestBody: PersonalOfferPublishInput,
    ): CancelablePromise<ManagerPersonalOfferResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/personal-offers/{offer_id}/publish',
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
    /**
     * Revoke Manager Personal Offer
     * Immediately make the active link unavailable while retaining the draft.
     * @param offerId
     * @param requestBody
     * @returns ManagerPersonalOfferResponse Successful Response
     * @throws ApiError
     */
    public static revokeManagerPersonalOffer(
        offerId: number,
        requestBody: PersonalOfferVersionInput,
    ): CancelablePromise<ManagerPersonalOfferResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/personal-offers/{offer_id}/revoke',
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
