/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerCommercialDocumentDefaults } from '../models/ManagerCommercialDocumentDefaults';
import type { ManagerCommercialTermsExtract } from '../models/ManagerCommercialTermsExtract';
import type { ManagerCommercialTermsResponse } from '../models/ManagerCommercialTermsResponse';
import type { ManagerCommercialTermsUpdate } from '../models/ManagerCommercialTermsUpdate';
import type { ManagerOrderCreatePayload } from '../models/ManagerOrderCreatePayload';
import type { ManagerOrderDetailResponse } from '../models/ManagerOrderDetailResponse';
import type { ManagerOrderDocumentGeneratePayload } from '../models/ManagerOrderDocumentGeneratePayload';
import type { ManagerOrderDocumentResponse } from '../models/ManagerOrderDocumentResponse';
import type { ManagerOrderExportRequest } from '../models/ManagerOrderExportRequest';
import type { ManagerOrderImportCommitRequest } from '../models/ManagerOrderImportCommitRequest';
import type { ManagerOrderImportCommitResponse } from '../models/ManagerOrderImportCommitResponse';
import type { ManagerOrderImportPreviewRequest } from '../models/ManagerOrderImportPreviewRequest';
import type { ManagerOrderImportPreviewResponse } from '../models/ManagerOrderImportPreviewResponse';
import type { ManagerOrderListResponse } from '../models/ManagerOrderListResponse';
import type { ManagerOrderScenariosResponse } from '../models/ManagerOrderScenariosResponse';
import type { ManagerOrderSourceAnalyze } from '../models/ManagerOrderSourceAnalyze';
import type { ManagerOrderSourceApply } from '../models/ManagerOrderSourceApply';
import type { ManagerOrderSourceApplyResult } from '../models/ManagerOrderSourceApplyResult';
import type { ManagerOrderSourceCard } from '../models/ManagerOrderSourceCard';
import type { ManagerOrderSourceEquipmentAdd } from '../models/ManagerOrderSourceEquipmentAdd';
import type { ManagerOrderSourceEquipmentPreview } from '../models/ManagerOrderSourceEquipmentPreview';
import type { ManagerOrderSourcePreview } from '../models/ManagerOrderSourcePreview';
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
import type { SourceEquipmentPrefillResult } from '../models/SourceEquipmentPrefillResult';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerOrdersService {
    /**
     * List Manager Order Scenarios
     * Read the shared allowed order scenario dictionary. Manager access is required; this
     * response is configuration metadata, not a list of tenant orders.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @returns ManagerOrderScenariosResponse Successful Response
     * @throws ApiError
     */
    public static listManagerOrderScenarios(): CancelablePromise<ManagerOrderScenariosResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/orders/scenarios',
        });
    }
    /**
     * Get Manager Orders
     * Page orders accessible in the current Manager tenant/storefront, applying customer
     * segment, status/search/overdue/customer and sort filters before projection. limit is at
     * most 100. Invalid business filters/sort return 400; response carries list metadata
     * rather than unrestricted platform CRM data.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param segment
     * @param page
     * @param limit
     * @param status
     * @param search
     * @param overdueOnly
     * @param sort
     * @param customerId
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
        customerId?: (number | null),
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
                'customer_id': customerId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Manager Order
     * Create an order in the current Manager tenant/storefront and return its detailed
     * projection. Customer/object/product/service/executor relationships are validated by the
     * command service; invalid context returns 400. This legacy creation has no caller
     * idempotency receipt; repeating POST can create another order.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * List at most 100 stale work stages in the current Manager tenant/storefront, using the
     * age threshold and optional unscheduled stages. Read-only: does not cancel/delete stages
     * or notify installers.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Export explicitly selected accessible orders as a transfer package in the current
     * Manager tenant/storefront. Missing/inaccessible selections or invalid export input
     * return 400. This POST is read-only; it does not transfer documents/provider files or
     * write a destination tenant.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Read the current Manager tenant/storefront order projection with proposals, lines,
     * stages and payment context. Missing or inaccessible order returns 404. Opening the
     * detail does not imply a client may edit another tenant’s IDs.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Patch supplied order/customer/commercial fields in the current Manager tenant/storefront
     * and return the refreshed projection. Commercial line arrays replace the targeted
     * proposal’s lines; line_proposal_id disambiguates empty arrays, and sent/accepted
     * proposal lines cannot be overwritten. A won order cannot close with unpaid balance;
     * closing lost can archive an otherwise unused customer. Missing order returns 404;
     * invalid relationships/transitions return 400. No expected_version or idempotency receipt
     * resolves concurrent field edits. See [order saving and proposal
     * scope](https://github.com/mvnby/air-api/blob/main/docs/manager-order-autosave.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Hard-delete an accessible scoped order together with
     * proposal/line/stage/executor/payment/document rows, enqueueing provider document
     * cleanup. Bank receipt and outgoing-email histories are detached for audit rather than
     * removed. Missing order/service validation returns 400; unexpected deletion failure 500.
     * No closed-order document lock is applied by this order-delete command; repeat after
     * deletion is not receipt replay.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Set a scoped stage to canceled without needing order_id and return its stale-stage
     * projection. Manager access is required; missing/inaccessible stage returns 404. Enqueues
     * a cancellation notification only on a status change; this is distinct from deleting the
     * stage.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Hard-delete a work stage accessible in the current tenant/storefront by stage_id and
     * return its removed ID. Missing/inaccessible stage returns 404, including a repeat after
     * deletion. Does not cancel the stage or use the cancellation notification command.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Validate an order transfer package and resolve customer/product matches in the current
     * Manager tenant/storefront without committing imported orders. Inspect can_import and
     * unresolved items/warnings; invalid package input returns 400. Product resolution remains
     * separate from import commit.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Import a transfer package into the current Manager tenant/storefront after rerunning
     * preview validation. Creates orders and related customer/object/line/stage/payment data
     * according to service options; inspect warnings/skipped-payments counts. Unresolved
     * products or invalid data return 400. No caller idempotency receipt is provided:
     * repeating commit can create duplicate orders.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Create a draft proposal under an accessible order in the current Manager
     * tenant/storefront, optionally copying an active proposal’s lines. Returns the refreshed
     * order and recalculates financial projection. Missing source/order or invalid context
     * returns 400; repeating POST can create another proposal.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Copy the selected active proposal into a new draft under its scoped order; the path
     * proposal_id supplies the copy source. Returns the refreshed order. Missing/inaccessible
     * source/order returns 400. Repeating POST creates another copy rather than replaying a
     * receipt.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Patch supplied proposal name/status/order/archive metadata under the current
     * tenant/storefront order. Ready-to-send requires nonempty lines and positive total;
     * archived selected proposals can select an active replacement. Recalculates order
     * financial/status projection. Missing proposal/order or invalid state returns 400.
     * Commercial lines are edited through the order command.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Archive a proposal under the current tenant/storefront order. If selected, chooses an
     * active replacement when available and refreshes order financial/status projection.
     * Missing proposal/order or invalid context returns 400. Archiving retains the proposal
     * rather than hard-deleting its history.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Select an active proposal belonging to an accessible scoped order, unselect siblings and
     * refresh order status/financial projection. Missing/archived/foreign-order proposal
     * returns 400. Selection does not copy or issue a document.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Generate or reuse a legacy Google document for the current tenant/storefront order using
     * the selected proposal, template and basis/scope. Closed orders return 409; invalid
     * type/basis/line selection/date returns 400 and unexpected generation failure 500.
     * Proposal/closing document kinds create new records; eligible legacy records of other
     * kinds can be reused by template. Supplied additional_conditions updates order conditions
     * and forces a new document. No generic idempotency receipt is provided. Native lifecycle
     * endpoints are separate. See the [document lifecycle
     * contract](https://github.com/mvnby/air-api/blob/main/docs/document-module-architecture.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * @param scopeServiceLineQuantities JSON map/list of service line quantities included in scoped closing document
     * @param scopeProductLineIds Order product line IDs included in scoped closing document
     * @param requestBody
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
        scopeServiceLineQuantities?: (string | null),
        scopeProductLineIds?: (Array<number> | null),
        requestBody?: (ManagerOrderDocumentGeneratePayload | null),
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
                'scope_service_line_quantities': scopeServiceLineQuantities,
                'scope_product_line_ids': scopeProductLineIds,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Add Manager Order Payment
     * Record a payment on an accessible scoped order and refresh financial totals, returning
     * its payment list. Non-BYN currency must match the order target currency. Missing order
     * returns 404; invalid type/currency returns 400. POST is additive with no caller
     * idempotency receipt; reconcile before retrying.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Remove a payment from an accessible scoped order and refresh affected finances. For a
     * bank-linked payment, removes all payments from that receipt across accessible orders and
     * returns the receipt to requires_review; cross-tenant allocations are refused. Missing
     * order returns 404; missing/wrong-order payment or invalid allocation returns 400.
     * Returns the selected order’s remaining payment list.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Create a work stage under the current tenant/storefront order, checking executor
     * assignment and scheduling and enqueuing relevant staff notification events. Returns the
     * refreshed order; invalid/missing order or executor context returns 400. Repeating POST
     * can add another stage.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Patch a stage belonging to the specified scoped order. Validates changed executor and
     * normalizes times/status; assignment, rescheduling and cancellation can enqueue staff
     * notification events. Completion of all stages with outstanding balance can put the order
     * on hold. Missing stage or invalid context returns 400; returns the refreshed order.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Hard-delete a stage belonging to the specified order in the current tenant/storefront
     * and return the refreshed order projection. Missing/wrong-order stage returns 400,
     * including a repeat after deletion. This is not the direct stage-cancellation workflow.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
    /**
     * Get Manager Order Source Card
     * Read locally saved reviewed Belzakupki evidence and private original-attachment metadata
     * for an accessible order in the current tenant/storefront. Does not fetch new source
     * detail or invoke AI. Missing order returns 404; missing/invalid source identity returns
     * 400. See [source review and equipment
     * rules](https://github.com/mvnby/air-api/blob/main/docs/belzakupki-intake.md#manager-review-and-source-documents).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param orderId
     * @returns ManagerOrderSourceCard Successful Response
     * @throws ApiError
     */
    public static getManagerOrderSourceCard(
        orderId: number,
    ): CancelablePromise<ManagerOrderSourceCard> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/orders/{order_id}/source-card',
            path: {
                'order_id': orderId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Manager Order Source Equipment
     * Preview exact catalog matches from locally reviewed source objects for an accessible
     * scoped order and selected proposal. Reports price/stock, existing lines and reasons
     * items cannot be added or need explicit restoration; no lines are changed. Missing order
     * returns 404 and invalid proposal/source context 400. Returned preview_fingerprint is
     * required by the explicit add command. See [source review and equipment
     * rules](https://github.com/mvnby/air-api/blob/main/docs/belzakupki-intake.md#manager-review-and-source-documents).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param orderId
     * @param proposalId
     * @returns ManagerOrderSourceEquipmentPreview Successful Response
     * @throws ApiError
     */
    public static getManagerOrderSourceEquipment(
        orderId: number,
        proposalId?: (number | null),
    ): CancelablePromise<ManagerOrderSourceEquipmentPreview> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/orders/{order_id}/source-equipment',
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
     * Add Manager Order Source Equipment
     * Append explicitly selected exact source-equipment matches to a writable draft proposal
     * in the current tenant/storefront; existing lines/prices/quantities are preserved.
     * Rechecks preview_fingerprint under the order lock: changed proposal/source/price/stock
     * returns 409. Missing order returns 404; invalid selection or read-only context 400.
     * Repeat the same command_id and selection to reuse its stored result; restoring
     * previously removed items requires explicit restore IDs. See [source review and equipment
     * rules](https://github.com/mvnby/air-api/blob/main/docs/belzakupki-intake.md#manager-review-and-source-documents).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param orderId
     * @param requestBody
     * @returns SourceEquipmentPrefillResult Successful Response
     * @throws ApiError
     */
    public static addManagerOrderSourceEquipment(
        orderId: number,
        requestBody: ManagerOrderSourceEquipmentAdd,
    ): CancelablePromise<SourceEquipmentPrefillResult> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/source-equipment',
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
     * Get Manager Order Source Preview
     * Fetch fresh Belzakupki source detail for the accessible current-tenant/storefront order
     * and build a reviewable customer/site/equipment/submission/terms draft. Registry lookup
     * can add warnings. Does not save customer/order changes or invoke document AI. Missing
     * order/source returns 404, invalid source identity 400 and source/configuration failure
     * 502. See [source review and equipment
     * rules](https://github.com/mvnby/air-api/blob/main/docs/belzakupki-intake.md#manager-review-and-source-documents).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param orderId
     * @returns ManagerOrderSourcePreview Successful Response
     * @throws ApiError
     */
    public static getManagerOrderSourcePreview(
        orderId: number,
    ): CancelablePromise<ManagerOrderSourcePreview> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/orders/{order_id}/source-preview',
            path: {
                'order_id': orderId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Analyze Manager Order Source
     * Run explicit external AI analysis of selected original source documents for an
     * accessible order and return an editable preview. Requires system-tenant Manager access.
     * May fetch originals and extract missing text; does not apply the draft or overwrite
     * order/document values. Missing source/order returns 404, unknown/truncated document
     * input 400 and source/provider failure 502. Repeating starts another analysis rather than
     * replaying a receipt. See [source review and equipment
     * rules](https://github.com/mvnby/air-api/blob/main/docs/belzakupki-intake.md#manager-review-and-source-documents).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param orderId
     * @param requestBody
     * @returns ManagerOrderSourcePreview Successful Response
     * @throws ApiError
     */
    public static analyzeManagerOrderSource(
        orderId: number,
        requestBody: ManagerOrderSourceAnalyze,
    ): CancelablePromise<ManagerOrderSourcePreview> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/source-analyze',
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
     * Apply Manager Order Source
     * Apply reviewed Belzakupki evidence to an accessible order in the current
     * tenant/storefront. Can attach/create the reviewed customer and address branches, save
     * source metadata/terms, select a scenario and move a new lead to negotiation, copy
     * selected originals privately and prefill exact equipment for sales+installation.
     * Archived incoming records, conflicting customer/scenario or invalid originals return
     * 400; missing source/order 404, source failure 502. Existing private originals/equipment
     * provenance can be reused, but no generic command receipt or expected_version check is
     * supplied. See [source review and equipment
     * rules](https://github.com/mvnby/air-api/blob/main/docs/belzakupki-intake.md#manager-review-and-source-documents).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param orderId
     * @param requestBody
     * @returns ManagerOrderSourceApplyResult Successful Response
     * @throws ApiError
     */
    public static applyManagerOrderSource(
        orderId: number,
        requestBody: ManagerOrderSourceApply,
    ): CancelablePromise<ManagerOrderSourceApplyResult> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/source-apply',
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
     * Download Manager Order Source Document
     * Fetch an original document identified by the accessible order’s saved Belzakupki source
     * in the current tenant/storefront. Returns a private/no-store binary attachment with
     * detected file type. Missing source/order/document returns 404; invalid identity or
     * document above configured attachment-size limit 400; upstream/configuration failure 502.
     * Download does not copy it into the order’s private attachments.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param orderId
     * @param documentId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static downloadManagerOrderSourceDocument(
        orderId: number,
        documentId: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/orders/{order_id}/source-documents/{document_id}',
            path: {
                'order_id': orderId,
                'document_id': documentId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Terms
     * Read customer-requested source evidence separately from proposed business terms, review
     * confirmation and current revision. Missing or inaccessible order returns 404. Reading
     * fallback evidence does not save or confirm it.
     *
     * Access and scope: Manager access is required; the order and its children are restricted
     * to the authenticated tenant and selected storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param orderId
     * @returns ManagerCommercialTermsResponse Successful Response
     * @throws ApiError
     */
    public static getManagerOrderCommercialTerms(
        orderId: number,
    ): CancelablePromise<ManagerCommercialTermsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/orders/{order_id}/commercial-terms',
            path: {
                'order_id': orderId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Terms
     * Save proposed business terms and their confirmation under an order lock.
     * expected_revision must match or the command returns 409; each successful edit increments
     * the revision, so replaying an old revision conflicts. Missing order returns 404 and demo
     * mutations return 403. Source evidence is preserved independently of the negotiated
     * terms.
     *
     * Access and scope: Manager access is required; the order and its children are restricted
     * to the authenticated tenant and selected storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param orderId
     * @param requestBody
     * @returns ManagerCommercialTermsResponse Successful Response
     * @throws ApiError
     */
    public static updateManagerOrderCommercialTerms(
        orderId: number,
        requestBody: ManagerCommercialTermsUpdate,
    ): CancelablePromise<ManagerCommercialTermsResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/orders/{order_id}/commercial-terms',
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
     * Extract Terms
     * Extract customer-requested commercial conditions from saved order source context and up
     * to eight selected scoped order attachments, then merge source evidence with duplicate
     * evidence suppressed. Proposed business terms, review confirmation and revision are
     * preserved. Missing order/attachment returns 404, invalid extraction input 400 and demo
     * mutation 403. This saves extracted evidence; it does not accept those conditions or
     * change document defaults.
     *
     * Access and scope: Manager access is required; the order and its children are restricted
     * to the authenticated tenant and selected storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param orderId
     * @param requestBody
     * @returns ManagerCommercialTermsResponse Successful Response
     * @throws ApiError
     */
    public static extractManagerOrderCommercialTerms(
        orderId: number,
        requestBody: ManagerCommercialTermsExtract,
    ): CancelablePromise<ManagerCommercialTermsResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/commercial-terms/extract',
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
     * Get Defaults
     * Read document defaults derived from the order’s reviewed commercial terms. Business
     * terms are returned only when the proposed terms are valid and confirmed; otherwise they
     * are absent. Missing or inaccessible order returns 404; this does not create a document
     * or confirm terms.
     *
     * Access and scope: Manager access is required; the order and its children are restricted
     * to the authenticated tenant and selected storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param orderId
     * @returns ManagerCommercialDocumentDefaults Successful Response
     * @throws ApiError
     */
    public static getManagerOrderCommercialDocumentDefaults(
        orderId: number,
    ): CancelablePromise<ManagerCommercialDocumentDefaults> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/orders/{order_id}/commercial-terms/document-defaults',
            path: {
                'order_id': orderId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
