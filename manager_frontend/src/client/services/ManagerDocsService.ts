/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerActionMessageResponse } from '../models/ManagerActionMessageResponse';
import type { ManagerOrderDocumentListResponse } from '../models/ManagerOrderDocumentListResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerDocsService {
    /**
     * Get Manager Order Documents
     * @param orderId
     * @returns ManagerOrderDocumentListResponse Successful Response
     * @throws ApiError
     */
    public static getManagerOrderDocuments(
        orderId: number,
    ): CancelablePromise<ManagerOrderDocumentListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/orders/{order_id}/documents',
            path: {
                'order_id': orderId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Manager Doc Download
     * @param docId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getManagerDocDownload(
        docId: number,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/docs/{doc_id}/download',
            path: {
                'doc_id': docId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Manager Doc
     * @param docId
     * @returns ManagerActionMessageResponse Successful Response
     * @throws ApiError
     */
    public static deleteManagerDoc(
        docId: number,
    ): CancelablePromise<ManagerActionMessageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/docs/{doc_id}',
            path: {
                'doc_id': docId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
