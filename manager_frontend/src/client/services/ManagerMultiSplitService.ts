/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerMultiSplitPreviewResponse } from '../models/ManagerMultiSplitPreviewResponse';
import type { ManagerMultiSplitSavePayload } from '../models/ManagerMultiSplitSavePayload';
import type { ManagerOrderDetailResponse } from '../models/ManagerOrderDetailResponse';
import type { MultiSplitOptionsResponse } from '../models/MultiSplitOptionsResponse';
import type { MultiSplitPreviewRequest } from '../models/MultiSplitPreviewRequest';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerMultiSplitService {
    /**
     * List Manager Multi Split Options
     * @param kind
     * @param page
     * @param limit
     * @returns MultiSplitOptionsResponse Successful Response
     * @throws ApiError
     */
    public static listManagerMultiSplitOptions(
        kind: 'outdoor_unit' | 'indoor_unit',
        page: number = 1,
        limit: number = 40,
    ): CancelablePromise<MultiSplitOptionsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/multi-split/options',
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
     * Preview Manager Multi Split
     * @param requestBody
     * @returns ManagerMultiSplitPreviewResponse Successful Response
     * @throws ApiError
     */
    public static previewManagerMultiSplit(
        requestBody: MultiSplitPreviewRequest,
    ): CancelablePromise<ManagerMultiSplitPreviewResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/multi-split/preview',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Save Manager Multi Split Proposal
     * @param orderId
     * @param requestBody
     * @returns ManagerOrderDetailResponse Successful Response
     * @throws ApiError
     */
    public static saveManagerMultiSplitProposal(
        orderId: number,
        requestBody: ManagerMultiSplitSavePayload,
    ): CancelablePromise<ManagerOrderDetailResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/multi-split/orders/{order_id}/proposals',
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
}
