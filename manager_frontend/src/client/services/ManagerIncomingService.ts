/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { IncomingCreatePayload } from '../models/IncomingCreatePayload';
import type { IncomingListResponse } from '../models/IncomingListResponse';
import type { IncomingResponse } from '../models/IncomingResponse';
import type { IncomingUpdatePayload } from '../models/IncomingUpdatePayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerIncomingService {
    /**
     * Create Incoming
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
