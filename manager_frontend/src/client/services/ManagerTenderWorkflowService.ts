/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TenderWorkflowIdentity } from '../models/TenderWorkflowIdentity';
import type { TenderWorkflowLinkPayload } from '../models/TenderWorkflowLinkPayload';
import type { TenderWorkflowPayload } from '../models/TenderWorkflowPayload';
import type { TenderWorkflowResponse } from '../models/TenderWorkflowResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerTenderWorkflowService {
    /**
     * Get Workflow
     * Read manual tender stage/current deadline and associated distinct Orders in the current tenant/storefront,
     * including qualified and archived email/Bel tender sources. Source external IDs, statuses, archives,
     * documents and proposals remain independent. Returns at most 100 latest stage/link audit events;
     * reading neither marks an inbox record read nor creates associations. Missing/ineligible or foreign
     * Order returns 404; a continuation email already linked to another Order returns 409.
     *
     * Requires authenticated Manager session/JWT, live membership and scoped order-read permission; see
     * [Manager access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param orderId
     * @returns TenderWorkflowResponse Successful Response
     * @throws ApiError
     */
    public static getManagerTenderWorkflow(
        orderId: number,
    ): CancelablePromise<TenderWorkflowResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/orders/{order_id}/tender-workflow',
            path: {
                'order_id': orderId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Set Workflow
     * Set the business stage and current stage deadline for an email/Bel tender Order in the current
     * tenant/storefront, including qualified/archived sources. Audit author/time and before/after values;
     * the importer cannot overwrite this separate manual context. Explicit null clears the current
     * deadline; omission preserves it on the same stage and clears it on a stage change. Does not submit
     * to a procurement platform or change Order status/archive. Missing/foreign Order returns 404,
     * stage-role conflict on an existing association returns 409, demo mutation 403 and invalid stage
     * or timezone-less deadline 422. Same-value repeat is idempotent; no replay receipt is provided.
     *
     * Requires authenticated Manager session/JWT, live membership and scoped order-update permission; see
     * [Manager access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param orderId
     * @param requestBody
     * @returns TenderWorkflowResponse Successful Response
     * @throws ApiError
     */
    public static setManagerTenderWorkflow(
        orderId: number,
        requestBody: TenderWorkflowPayload,
    ): CancelablePromise<TenderWorkflowResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/orders/{order_id}/tender-workflow',
            path: {
                'order_id': orderId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Candidates
     * Search previous email/Bel tender Orders only within the current tenant/storefront, including
     * qualified and archived records. Include unmarked sources and explicitly marked price_request/
     * price_sent sources; selecting an unmarked candidate requires an explicit stage command before
     * association. Buyer/title similarity never creates a match. Search is at most 200 characters;
     * limit is 1..100 (default 20), ordered newest first. Missing/foreign current Order returns 404,
     * ineligible continuation email 409 and invalid query 422. Read-only and does not mark read.
     *
     * Requires authenticated Manager session/JWT, live membership and scoped order-read permission; see
     * [Manager access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param orderId
     * @param search
     * @param limit
     * @returns TenderWorkflowIdentity Successful Response
     * @throws ApiError
     */
    public static listManagerTenderPriceEnquiries(
        orderId: number,
        search?: (string | null),
        limit: number = 20,
    ): CancelablePromise<Array<TenderWorkflowIdentity>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/orders/{order_id}/tender-workflow/price-enquiries',
            path: {
                'order_id': orderId,
            },
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
     * Associate
     * Associate a later email/Bel tender publication with one manually marked price_request/price_sent
     * Order in the same tenant/storefront, including qualified/archived enquiries with different external
     * IDs. Audit both identities and preserve their independent documents/proposals/status/archive.
     * An unmarked publication gains announced stage and retains its source deadline. No automatic
     * match or platform submission. Missing/foreign endpoint returns 404; self-link, role conflict,
     * cycles/chains or replacing another link returns 409; demo mutation 403 and invalid payload 422.
     * Repeating the same pair is idempotent without a replay receipt; remove the current link before
     * selecting another price enquiry.
     *
     * Requires authenticated Manager session/JWT, live membership and scoped order-update permission; see
     * [Manager access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param orderId
     * @param requestBody
     * @returns TenderWorkflowResponse Successful Response
     * @throws ApiError
     */
    public static linkManagerTenderPriceEnquiry(
        orderId: number,
        requestBody: TenderWorkflowLinkPayload,
    ): CancelablePromise<TenderWorkflowResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/orders/{order_id}/tender-workflow/price-enquiry',
            path: {
                'order_id': orderId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Dissociate
     * Remove only the publication's manual price-enquiry association in the current tenant/storefront.
     * Audit both records and retain original identities, stages/deadlines, documents, proposals, status,
     * archives and earlier history. Missing/foreign Order returns 404; ineligible continuation email or
     * concurrently replaced association 409 and demo mutation 403. Repeating an already removed link
     * is idempotent without a replay receipt.
     *
     * Requires authenticated Manager session/JWT, live membership and scoped order-update permission; see
     * [Manager access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param orderId
     * @returns TenderWorkflowResponse Successful Response
     * @throws ApiError
     */
    public static unlinkManagerTenderPriceEnquiry(
        orderId: number,
    ): CancelablePromise<TenderWorkflowResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/orders/{order_id}/tender-workflow/price-enquiry',
            path: {
                'order_id': orderId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
