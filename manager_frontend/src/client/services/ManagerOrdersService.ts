/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerOrderCreatePayload } from '../models/ManagerOrderCreatePayload';
import type { ManagerOrderDetailResponse } from '../models/ManagerOrderDetailResponse';
import type { ManagerOrderDocumentResponse } from '../models/ManagerOrderDocumentResponse';
import type { ManagerOrderExportRequest } from '../models/ManagerOrderExportRequest';
import type { ManagerOrderImportCommitRequest } from '../models/ManagerOrderImportCommitRequest';
import type { ManagerOrderImportCommitResponse } from '../models/ManagerOrderImportCommitResponse';
import type { ManagerOrderImportPreviewRequest } from '../models/ManagerOrderImportPreviewRequest';
import type { ManagerOrderImportPreviewResponse } from '../models/ManagerOrderImportPreviewResponse';
import type { ManagerOrderListResponse } from '../models/ManagerOrderListResponse';
import type { ManagerOrderTransferPackage_Output } from '../models/ManagerOrderTransferPackage_Output';
import type { ManagerOrderUpdatePayload } from '../models/ManagerOrderUpdatePayload';
import type { ManagerStaleWorkStageItem } from '../models/ManagerStaleWorkStageItem';
import type { ManagerStaleWorkStageListResponse } from '../models/ManagerStaleWorkStageListResponse';
import type { OrderProposalCreatePayload } from '../models/OrderProposalCreatePayload';
import type { OrderProposalUpdatePayload } from '../models/OrderProposalUpdatePayload';
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
     * List Manager Stale Order Stages
     * @param olderThanDays
     * @param includeUnscheduled
     * @param limit
     * @returns ManagerStaleWorkStageListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerStaleOrderStages(
        olderThanDays: number = 7,
        includeUnscheduled: boolean = true,
        limit: number = 100,
    ): CancelablePromise<ManagerStaleWorkStageListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/orders/work-stages/stale',
            query: {
                'older_than_days': olderThanDays,
                'include_unscheduled': includeUnscheduled,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Export Manager Orders
     * @param requestBody
     * @returns ManagerOrderTransferPackage_Output Successful Response
     * @throws ApiError
     */
    public static exportManagerOrders(
        requestBody: ManagerOrderExportRequest,
    ): CancelablePromise<ManagerOrderTransferPackage_Output> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/export',
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
     * Cancel Manager Order Stage Direct
     * @param stageId
     * @returns ManagerStaleWorkStageItem Successful Response
     * @throws ApiError
     */
    public static cancelManagerOrderStageDirect(
        stageId: number,
    ): CancelablePromise<ManagerStaleWorkStageItem> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/orders/work-stages/{stage_id}/cancel',
            path: {
                'stage_id': stageId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Manager Order Stage Direct
     * @param stageId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static deleteManagerOrderStageDirect(
        stageId: number,
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/orders/work-stages/{stage_id}',
            path: {
                'stage_id': stageId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Preview Import Manager Orders
     * @param requestBody
     * @returns ManagerOrderImportPreviewResponse Successful Response
     * @throws ApiError
     */
    public static previewImportManagerOrders(
        requestBody: ManagerOrderImportPreviewRequest,
    ): CancelablePromise<ManagerOrderImportPreviewResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/import/preview',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Import Manager Orders
     * @param requestBody
     * @returns ManagerOrderImportCommitResponse Successful Response
     * @throws ApiError
     */
    public static importManagerOrders(
        requestBody: ManagerOrderImportCommitRequest,
    ): CancelablePromise<ManagerOrderImportCommitResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/import',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Manager Order Proposal
     * @param orderId
     * @param requestBody
     * @returns ManagerOrderDetailResponse Successful Response
     * @throws ApiError
     */
    public static createManagerOrderProposal(
        orderId: number,
        requestBody: OrderProposalCreatePayload,
    ): CancelablePromise<ManagerOrderDetailResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/proposals',
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
     * Duplicate Manager Order Proposal
     * @param orderId
     * @param proposalId
     * @param requestBody
     * @returns ManagerOrderDetailResponse Successful Response
     * @throws ApiError
     */
    public static duplicateManagerOrderProposal(
        orderId: number,
        proposalId: number,
        requestBody: OrderProposalCreatePayload,
    ): CancelablePromise<ManagerOrderDetailResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/proposals/{proposal_id}/duplicate',
            path: {
                'order_id': orderId,
                'proposal_id': proposalId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Patch Manager Order Proposal
     * @param orderId
     * @param proposalId
     * @param requestBody
     * @returns ManagerOrderDetailResponse Successful Response
     * @throws ApiError
     */
    public static patchManagerOrderProposal(
        orderId: number,
        proposalId: number,
        requestBody: OrderProposalUpdatePayload,
    ): CancelablePromise<ManagerOrderDetailResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/orders/{order_id}/proposals/{proposal_id}',
            path: {
                'order_id': orderId,
                'proposal_id': proposalId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Archive Manager Order Proposal
     * @param orderId
     * @param proposalId
     * @returns ManagerOrderDetailResponse Successful Response
     * @throws ApiError
     */
    public static archiveManagerOrderProposal(
        orderId: number,
        proposalId: number,
    ): CancelablePromise<ManagerOrderDetailResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/proposals/{proposal_id}/archive',
            path: {
                'order_id': orderId,
                'proposal_id': proposalId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Select Manager Order Proposal
     * @param orderId
     * @param proposalId
     * @returns ManagerOrderDetailResponse Successful Response
     * @throws ApiError
     */
    public static selectManagerOrderProposal(
        orderId: number,
        proposalId: number,
    ): CancelablePromise<ManagerOrderDetailResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/proposals/{proposal_id}/select',
            path: {
                'order_id': orderId,
                'proposal_id': proposalId,
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
     * @param proposalId Order proposal ID for generated commercial offer
     * @param baseDocumentId Order document ID used as basis for closing documents; 0 means selected open customer contract
     * @param scopeCustomerBranchId Customer branch/object for scoped closing document
     * @param scopeTitle Human-readable object title for scoped closing document
     * @param scopeAddress Object address override for scoped closing document
     * @param scopeServiceLineIds Order service line IDs included in scoped closing document
     * @param scopeProductLineIds Order product line IDs included in scoped closing document
     * @returns ManagerOrderDocumentResponse Successful Response
     * @throws ApiError
     */
    public static generateManagerOrderDocument(
        orderId: number,
        docType: string,
        documentTemplateId?: (number | null),
        templateId?: (string | null),
        contractDate?: (string | null),
        proposalId?: (number | null),
        baseDocumentId?: (number | null),
        scopeCustomerBranchId?: (number | null),
        scopeTitle?: (string | null),
        scopeAddress?: (string | null),
        scopeServiceLineIds?: (Array<number> | null),
        scopeProductLineIds?: (Array<number> | null),
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
                'proposal_id': proposalId,
                'base_document_id': baseDocumentId,
                'scope_customer_branch_id': scopeCustomerBranchId,
                'scope_title': scopeTitle,
                'scope_address': scopeAddress,
                'scope_service_line_ids': scopeServiceLineIds,
                'scope_product_line_ids': scopeProductLineIds,
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
