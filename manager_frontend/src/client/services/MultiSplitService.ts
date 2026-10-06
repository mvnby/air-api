/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MultiSplitLeadPayload } from '../models/MultiSplitLeadPayload';
import type { MultiSplitLeadResponse } from '../models/MultiSplitLeadResponse';
import type { MultiSplitOptionsResponse } from '../models/MultiSplitOptionsResponse';
import type { MultiSplitPreviewRequest } from '../models/MultiSplitPreviewRequest';
import type { MultiSplitPreviewResponse } from '../models/MultiSplitPreviewResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class MultiSplitService {
    /**
     * List Public Multi Split Options
     * List storefront-visible indoor or outdoor units for multi-split selection, with public
     * prices and pagination; limit is at most 100.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @param kind
     * @param page
     * @param limit
     * @returns MultiSplitOptionsResponse Successful Response
     * @throws ApiError
     */
    public static listPublicMultiSplitOptions(
        kind: 'outdoor_unit' | 'indoor_unit',
        page: number = 1,
        limit: number = 40,
    ): CancelablePromise<MultiSplitOptionsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/multi-split/options',
            query: {
                'kind': kind,
                'page': page,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Preview Public Multi Split
     * Validate a multi-split selection server-side in the resolved storefront and return its
     * public price projection without creating a lead. Invalid or incompatible selection
     * returns 422.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @param requestBody
     * @returns MultiSplitPreviewResponse Successful Response
     * @throws ApiError
     */
    public static previewPublicMultiSplit(
        requestBody: MultiSplitPreviewRequest,
    ): CancelablePromise<MultiSplitPreviewResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/multi-split/preview',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Public Multi Split Lead
     * Validate a multi-split selection and create a lead in this storefront. Idempotency-Key
     * is required; invalid selection or intake values return 422. For required keys, unsigned
     * compatibility, conflicting payloads (409) and retries after 503 with Retry-After, see
     * [public write
     * idempotency](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#public-write-idempotency).
     * Retain the same key and content when retrying.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @param idempotencyKey
     * @param requestBody
     * @returns MultiSplitLeadResponse Successful Response
     * @throws ApiError
     */
    public static createPublicMultiSplitLead(
        idempotencyKey: string,
        requestBody: MultiSplitLeadPayload,
    ): CancelablePromise<MultiSplitLeadResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/multi-split/leads',
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
