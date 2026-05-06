/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerOrderCreatePayload } from '../models/ManagerOrderCreatePayload';
import type { ManagerOrderDetailResponse } from '../models/ManagerOrderDetailResponse';
import type { ManagerOrderDocumentResponse } from '../models/ManagerOrderDocumentResponse';
import type { ManagerOrderListResponse } from '../models/ManagerOrderListResponse';
import type { ManagerOrderUpdatePayload } from '../models/ManagerOrderUpdatePayload';
import type { OrderWorkStageCreatePayload } from '../models/OrderWorkStageCreatePayload';
import type { OrderWorkStageUpdatePayload } from '../models/OrderWorkStageUpdatePayload';
import type { PaymentCreatePayload } from '../models/PaymentCreatePayload';
import type { PaymentResponse } from '../models/PaymentResponse';
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
     * Delete Manager Order
     * @param orderId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static deleteManagerOrder(
        orderId: number,
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'DELETE',
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
     * Generate Manager Order Document
     * @param orderId
     * @param docType
     * @param documentTemplateId Managed document template ID
     * @param templateId Google Drive template file ID
     * @param contractDate Document/contract date as ISO datetime
     * @returns ManagerOrderDocumentResponse Successful Response
     * @throws ApiError
     */
    public static generateManagerOrderDocument(
        orderId: number,
        docType: string,
        documentTemplateId?: (number | null),
        templateId?: (string | null),
        contractDate?: (string | null),
    ): CancelablePromise<ManagerOrderDocumentResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/documents/{doc_type}',
            path: {
                'order_id': orderId,
                'doc_type': docType,
            },
            query: {
                'document_template_id': documentTemplateId,
                'template_id': templateId,
                'contract_date': contractDate,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Add Manager Order Payment
     * @param orderId
     * @param requestBody
     * @returns PaymentResponse Successful Response
     * @throws ApiError
     */
    public static addManagerOrderPayment(
        orderId: number,
        requestBody: PaymentCreatePayload,
    ): CancelablePromise<Array<PaymentResponse>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/payments',
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
     * Delete Manager Order Payment
     * @param orderId
     * @param paymentId
     * @returns PaymentResponse Successful Response
     * @throws ApiError
     */
    public static deleteManagerOrderPayment(
        orderId: number,
        paymentId: number,
    ): CancelablePromise<Array<PaymentResponse>> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/orders/{order_id}/payments/{payment_id}',
            path: {
                'order_id': orderId,
                'payment_id': paymentId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Manager Order Stage
     * @param orderId
     * @param requestBody
     * @returns ManagerOrderDetailResponse Successful Response
     * @throws ApiError
     */
    public static createManagerOrderStage(
        orderId: number,
        requestBody: OrderWorkStageCreatePayload,
    ): CancelablePromise<ManagerOrderDetailResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/stages',
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
     * Update Manager Order Stage
     * @param orderId
     * @param stageId
     * @param requestBody
     * @returns ManagerOrderDetailResponse Successful Response
     * @throws ApiError
     */
    public static updateManagerOrderStage(
        orderId: number,
        stageId: number,
        requestBody: OrderWorkStageUpdatePayload,
    ): CancelablePromise<ManagerOrderDetailResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/orders/{order_id}/stages/{stage_id}',
            path: {
                'order_id': orderId,
                'stage_id': stageId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Manager Order Stage
     * @param orderId
     * @param stageId
     * @returns ManagerOrderDetailResponse Successful Response
     * @throws ApiError
     */
    public static deleteManagerOrderStage(
        orderId: number,
        stageId: number,
    ): CancelablePromise<ManagerOrderDetailResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/orders/{order_id}/stages/{stage_id}',
            path: {
                'order_id': orderId,
                'stage_id': stageId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
