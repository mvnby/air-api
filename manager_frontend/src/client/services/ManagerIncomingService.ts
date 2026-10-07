/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { IncomingClarificationPayload } from '../models/IncomingClarificationPayload';
import type { IncomingCreatePayload } from '../models/IncomingCreatePayload';
import type { IncomingListResponse } from '../models/IncomingListResponse';
import type { IncomingResponse } from '../models/IncomingResponse';
import type { IncomingUpdatePayload } from '../models/IncomingUpdatePayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerIncomingService {
    /**
     * Create Clarification
     * Explicitly create one linked address/call clarification task from the known
     * incoming context for the authenticated Manager actor's tenant/storefront. The
     * task is assigned to the caller without a deadline or reminder; a customer wish
     * never becomes a callback deadline or booked visit. Requires expected_version
     * and Idempotency-Key. Same command/key replays; changed payload/key, stale version
     * or terminal incoming returns 409, missing/inaccessible intake 404, demo 403,
     * invalid input/key 400/422 and unavailable receipt 503 with Retry-After: 1.
     * A new intentional command on the current version returns the existing link.
     * Task read/edit visibility remains the PersonalTask author/assignee contract.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see
     * [Manager access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param leadId
     * @param idempotencyKey
     * @param requestBody
     * @returns IncomingResponse Successful Response
     * @throws ApiError
     */
    public static createManagerIncomingClarification(
        leadId: number,
        idempotencyKey: string,
        requestBody: IncomingClarificationPayload,
    ): CancelablePromise<IncomingResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/incoming/{lead_id}/clarification',
            path: {
                'lead_id': leadId,
            },
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Incoming
     * Save an incomplete incoming request as a Lead in the authenticated staff actor’s
     * tenant/storefront, retaining original text/source time and reporting missing
     * contact/address data. Does not create a customer/order or reserve a work slot; inferred
     * phone/date remain suggestions. Requires Idempotency-Key: same actor/key/payload replays
     * with Idempotency-Replayed; changed key payload or reused source event with different
     * content returns 409. Invalid key returns 400, demo mutation 403, unavailable receipt
     * storage 503 with Retry-After: 1. Retry the unchanged command/key.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param idempotencyKey
     * @param requestBody
     * @returns IncomingResponse Successful Response
     * @throws ApiError
     */
    public static createManagerIncoming(
        idempotencyKey: string,
        requestBody: IncomingCreatePayload,
    ): CancelablePromise<IncomingResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/incoming',
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Incoming
     * List unconverted, unarchived incoming requests in new/contacted state for the
     * authenticated staff actor’s tenant/storefront, newest first. Uses limit/offset with
     * limit at most 100 and returns total. Does not mark personal read state, qualify a lead
     * or schedule requested time.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param limit
     * @param offset
     * @returns IncomingListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerIncoming(
        limit: number = 30,
        offset?: number,
    ): CancelablePromise<IncomingListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/incoming',
            query: {
                'limit': limit,
                'offset': offset,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Incoming
     * Read an incoming request with saved intake metadata in the authenticated staff actor’s
     * tenant/storefront, including current version, original text and missing-data state.
     * Missing/inaccessible or non-intake Lead returns 404. Reading does not mark the triage
     * card read or change its workflow.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param leadId
     * @returns IncomingResponse Successful Response
     * @throws ApiError
     */
    public static getManagerIncoming(
        leadId: number,
    ): CancelablePromise<IncomingResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/incoming/{lead_id}',
            path: {
                'lead_id': leadId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Incoming
     * Correct an active incoming request in the authenticated staff actor’s tenant/storefront
     * using expected_version and Idempotency-Key. Increments version, preserves omitted fields
     * and clears explicitly null optional fields; a changed time wish is reinterpreted only
     * against the retained source clock. Archived/qualified or changed-version request and
     * changed replay payload return 409; missing intake 404, demo mutation 403, invalid key
     * 400 and receipt storage unavailable 503 with Retry-After: 1. Same successful command/key
     * replays with Idempotency-Replayed; it does not reserve calendar time.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param leadId
     * @param idempotencyKey
     * @param requestBody
     * @returns IncomingResponse Successful Response
     * @throws ApiError
     */
    public static updateManagerIncoming(
        leadId: number,
        idempotencyKey: string,
        requestBody: IncomingUpdatePayload,
    ): CancelablePromise<IncomingResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/incoming/{lead_id}',
            path: {
                'lead_id': leadId,
            },
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
