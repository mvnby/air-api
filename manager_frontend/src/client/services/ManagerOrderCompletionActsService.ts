/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ConnectorWriteResult_OrderCompletionActPrepared_ } from '../models/ConnectorWriteResult_OrderCompletionActPrepared_';
import type { OrderCompletionActSource } from '../models/OrderCompletionActSource';
import type { PrepareOrderCompletionActPayload } from '../models/PrepareOrderCompletionActPayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerOrderCompletionActsService {
    /**
     * Get Order Completion Act Source
     * Read the current proposal revision before preparing a scoped closing act.
     * @param orderId
     * @param proposalId
     * @returns OrderCompletionActSource Successful Response
     * @throws ApiError
     */
    public static getManagerOrderCompletionActSource(
        orderId: number,
        proposalId: number,
    ): CancelablePromise<OrderCompletionActSource> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/orders/{order_id}/completion-acts/source',
            path: {
                'order_id': orderId,
            },
            query: {
                'proposal_id': proposalId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Prepare Order Completion Act
     * Prepare a standard closing-act draft using selected sites, one proposal and its basis.
     * @param orderId
     * @param requestBody
     * @returns ConnectorWriteResult_OrderCompletionActPrepared_ Successful Response
     * @throws ApiError
     */
    public static prepareManagerOrderCompletionAct(
        orderId: number,
        requestBody: PrepareOrderCompletionActPayload,
    ): CancelablePromise<ConnectorWriteResult_OrderCompletionActPrepared_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/completion-acts',
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
