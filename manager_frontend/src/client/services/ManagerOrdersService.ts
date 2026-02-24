/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerOrderCreatePayload } from '../models/ManagerOrderCreatePayload';
import type { ManagerOrderDetailResponse } from '../models/ManagerOrderDetailResponse';
import type { ManagerOrderDocumentResponse } from '../models/ManagerOrderDocumentResponse';
import type { ManagerOrderListResponse } from '../models/ManagerOrderListResponse';
import type { ManagerOrderUpdatePayload } from '../models/ManagerOrderUpdatePayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerOrdersService {
    /**
     * Get Manager Orders
     * @param segment
     * @param page
     * @param limit
     * @param status
     * @param search
     * @param overdueOnly
     * @param sort
     * @returns ManagerOrderListResponse Successful Response
     * @throws ApiError
     */
    public static getManagerOrders(
        segment: string = 'b2c',
        page: number = 1,
        limit: number = 20,
        status?: (string | null),
        search?: (string | null),
        overdueOnly: boolean = false,
        sort: string = 'created_at_desc',
    ): CancelablePromise<ManagerOrderListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/orders',
            query: {
                'segment': segment,
                'page': page,
                'limit': limit,
                'status': status,
                'search': search,
                'overdue_only': overdueOnly,
                'sort': sort,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Manager Order
     * @param requestBody
     * @returns ManagerOrderDetailResponse Successful Response
     * @throws ApiError
     */
    public static createManagerOrder(
        requestBody: ManagerOrderCreatePayload,
    ): CancelablePromise<ManagerOrderDetailResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Manager Order Detail
     * @param orderId
     * @returns ManagerOrderDetailResponse Successful Response
     * @throws ApiError
     */
    public static getManagerOrderDetail(
        orderId: number,
    ): CancelablePromise<ManagerOrderDetailResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/orders/{order_id}',
            path: {
                'order_id': orderId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Patch Manager Order
     * @param orderId
     * @param requestBody
     * @returns ManagerOrderDetailResponse Successful Response
     * @throws ApiError
     */
    public static patchManagerOrder(
        orderId: number,
        requestBody: ManagerOrderUpdatePayload,
    ): CancelablePromise<ManagerOrderDetailResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/orders/{order_id}',
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
     * Generate Manager Order Document
     * @param orderId
     * @param docType
     * @returns ManagerOrderDocumentResponse Successful Response
     * @throws ApiError
     */
    public static generateManagerOrderDocument(
        orderId: number,
        docType: string,
    ): CancelablePromise<ManagerOrderDocumentResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/documents/{doc_type}',
            path: {
                'order_id': orderId,
                'doc_type': docType,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
