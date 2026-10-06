/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_attach_internal_bot_task_stage_file_v1 } from '../models/Body_attach_internal_bot_task_stage_file_v1';
import type { Body_recognize_internal_bot_customer_requisites_file_v1 } from '../models/Body_recognize_internal_bot_customer_requisites_file_v1';
import type { BotApiHealthResponse } from '../models/BotApiHealthResponse';
import type { BotCatalogProductLookupResponse } from '../models/BotCatalogProductLookupResponse';
import type { BotCatalogSearchRequest } from '../models/BotCatalogSearchRequest';
import type { BotCatalogSearchResponse } from '../models/BotCatalogSearchResponse';
import type { BotCustomerRequisitesActionRequest } from '../models/BotCustomerRequisitesActionRequest';
import type { BotCustomerRequisitesActionResponse } from '../models/BotCustomerRequisitesActionResponse';
import type { BotCustomerRequisitesRecognitionResponse } from '../models/BotCustomerRequisitesRecognitionResponse';
import type { BotCustomerRequisitesTextRequest } from '../models/BotCustomerRequisitesTextRequest';
import type { BotQuickOrderCreateRequest } from '../models/BotQuickOrderCreateRequest';
import type { BotQuickOrderCreateResponse } from '../models/BotQuickOrderCreateResponse';
import type { BotQuickOrderCustomerSearchRequest } from '../models/BotQuickOrderCustomerSearchRequest';
import type { BotQuickOrderCustomerSearchResponse } from '../models/BotQuickOrderCustomerSearchResponse';
import type { BotQuickOrderDraftActionRequest } from '../models/BotQuickOrderDraftActionRequest';
import type { BotQuickOrderDraftPatchRequest } from '../models/BotQuickOrderDraftPatchRequest';
import type { BotQuickOrderDraftSessionResponse } from '../models/BotQuickOrderDraftSessionResponse';
import type { BotQuickOrderDraftStartRequest } from '../models/BotQuickOrderDraftStartRequest';
import type { BotQuickOrderParseRequest } from '../models/BotQuickOrderParseRequest';
import type { BotQuickOrderParseResponse } from '../models/BotQuickOrderParseResponse';
import type { BotStaffContextResponse } from '../models/BotStaffContextResponse';
import type { BotTaskAttachmentResponse } from '../models/BotTaskAttachmentResponse';
import type { BotTaskListRequest } from '../models/BotTaskListRequest';
import type { BotTaskListResponse } from '../models/BotTaskListResponse';
import type { BotTaskReportSaveRequest } from '../models/BotTaskReportSaveRequest';
import type { BotTaskReportSaveResponse } from '../models/BotTaskReportSaveResponse';
import type { BotTaskStatusUpdateRequest } from '../models/BotTaskStatusUpdateRequest';
import type { BotTaskStatusUpdateResponse } from '../models/BotTaskStatusUpdateResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class InternalBotV1Service {
    /**
     * Get Internal Bot Api Health
     * Check that the authenticated bot API is reachable and report its v1 contract marker.
     * Does not check a Telegram actor or database readiness.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
     * @returns BotApiHealthResponse Successful Response
     * @throws ApiError
     */
    public static getInternalBotApiHealthV1(): CancelablePromise<BotApiHealthResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/internal/bot/v1/health',
        });
    }
    /**
     * Get Internal Bot Staff Context
     * Resolve the active staff context of a Telegram identity, including Manager/executor
     * roles and legacy installer linkage. A non-staff identity is represented by
     * is_staff=false rather than a business permission grant.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
     * @param telegramId
     * @returns BotStaffContextResponse Successful Response
     * @throws ApiError
     */
    public static getInternalBotStaffContextV1(
        telegramId: number,
    ): CancelablePromise<BotStaffContextResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/internal/bot/v1/staff/context/{telegram_id}',
            path: {
                'telegram_id': telegramId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Search Internal Bot Catalog
     * Search the shared product catalog for an active staff Telegram actor (403 otherwise).
     * Returns internal bot product projections, not storefront-only catalog cards.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
     * @param requestBody
     * @returns BotCatalogSearchResponse Successful Response
     * @throws ApiError
     */
    public static searchInternalBotCatalogV1(
        requestBody: BotCatalogSearchRequest,
    ): CancelablePromise<BotCatalogSearchResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/catalog/search',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Internal Bot Catalog Product
     * Read one shared catalog product for an active staff Telegram actor (403 otherwise). A
     * missing product is product=null in a successful lookup response, not 404.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
     * @param productId
     * @param telegramId
     * @returns BotCatalogProductLookupResponse Successful Response
     * @throws ApiError
     */
    public static getInternalBotCatalogProductV1(
        productId: number,
        telegramId: number,
    ): CancelablePromise<BotCatalogProductLookupResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/internal/bot/v1/catalog/products/{product_id}',
            path: {
                'product_id': productId,
            },
            query: {
                'telegram_id': telegramId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Internal Bot My Tasks
     * Read work stages assigned to the actor’s linked installer in the system tenant, with
     * optional date/status filters. Active staff access is required (403 otherwise); staff
     * without an installer linkage receive an empty list.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
     * @param requestBody
     * @returns BotTaskListResponse Successful Response
     * @throws ApiError
     */
    public static listInternalBotMyTasksV1(
        requestBody: BotTaskListRequest,
    ): CancelablePromise<BotTaskListResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/tasks/my',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Internal Bot Task Status
     * Set the status of a stage assigned to the actor’s installer in the system tenant.
     * Missing/inaccessible/unassigned stage returns 403; an invalid state transition returns
     * 409. changed reports whether a transition occurred; this is not a generic idempotency
     * receipt.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
     * @param stageId
     * @param requestBody
     * @returns BotTaskStatusUpdateResponse Successful Response
     * @throws ApiError
     */
    public static updateInternalBotTaskStatusV1(
        stageId: number,
        requestBody: BotTaskStatusUpdateRequest,
    ): CancelablePromise<BotTaskStatusUpdateResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/tasks/stages/{stage_id}/status',
            path: {
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
     * Save Internal Bot Task Report
     * Save a normalized installer report on the actor’s assigned stage in the system tenant.
     * Missing/inaccessible stage returns 403. Repeating the same normalized report returns
     * changed=false.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
     * @param stageId
     * @param requestBody
     * @returns BotTaskReportSaveResponse Successful Response
     * @throws ApiError
     */
    public static saveInternalBotTaskReportV1(
        stageId: number,
        requestBody: BotTaskReportSaveRequest,
    ): CancelablePromise<BotTaskReportSaveResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/tasks/stages/{stage_id}/report',
            path: {
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
     * Attach Internal Bot Task Stage File
     * Attach a nonempty file of at most 10 MB to the actor’s assigned stage in the system
     * tenant. Inaccessible stage returns 403, empty content 422 and oversize content 413.
     * file_id provides attachment deduplication; inspect already_attached on retries.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
     * @param stageId
     * @param formData
     * @returns BotTaskAttachmentResponse Successful Response
     * @throws ApiError
     */
    public static attachInternalBotTaskStageFileV1(
        stageId: number,
        formData: Body_attach_internal_bot_task_stage_file_v1,
    ): CancelablePromise<BotTaskAttachmentResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/tasks/stages/{stage_id}/attachments',
            path: {
                'stage_id': stageId,
            },
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Parse Internal Bot Quick Order
     * Parse text into an editable quick-order draft for an active Manager Telegram actor (403
     * otherwise). Does not create an order or start a durable draft session.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
     * @param requestBody
     * @returns BotQuickOrderParseResponse Successful Response
     * @throws ApiError
     */
    public static parseInternalBotQuickOrderV1(
        requestBody: BotQuickOrderParseRequest,
    ): CancelablePromise<BotQuickOrderParseResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/quick-orders/parse',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Start Internal Bot Quick Order Draft
     * Start a durable quick-order draft owned by the active Manager Telegram actor in the
     * system tenant. The response supplies draft_id and version for subsequent edits. Access
     * denial returns 403, service draft conflicts 409 and invalid draft input 422.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
     * @param requestBody
     * @returns BotQuickOrderDraftSessionResponse Successful Response
     * @throws ApiError
     */
    public static startInternalBotQuickOrderDraftV1(
        requestBody: BotQuickOrderDraftStartRequest,
    ): CancelablePromise<BotQuickOrderDraftSessionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/quick-orders/drafts',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Search Internal Bot Quick Order Customers
     * Search customer candidates in the system tenant for an active Manager Telegram actor.
     * Access denial returns 403; invalid search input returns 422. Search does not create or
     * modify a customer.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
     * @param requestBody
     * @returns BotQuickOrderCustomerSearchResponse Successful Response
     * @throws ApiError
     */
    public static searchInternalBotQuickOrderCustomersV1(
        requestBody: BotQuickOrderCustomerSearchRequest,
    ): CancelablePromise<BotQuickOrderCustomerSearchResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/quick-orders/customers/search',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Internal Bot Quick Order Draft
     * Read a durable draft belonging to the active Manager Telegram actor. Access denial
     * returns 403; unavailable draft returns 404. Read version before issuing an edit or
     * action.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
     * @param draftId
     * @param telegramId
     * @returns BotQuickOrderDraftSessionResponse Successful Response
     * @throws ApiError
     */
    public static getInternalBotQuickOrderDraftV1(
        draftId: string,
        telegramId: number,
    ): CancelablePromise<BotQuickOrderDraftSessionResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/internal/bot/v1/quick-orders/drafts/{draft_id}',
            path: {
                'draft_id': draftId,
            },
            query: {
                'telegram_id': telegramId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Patch Internal Bot Quick Order Draft
     * Patch the actor’s active durable draft, checking expected_version and incrementing its
     * version. Requires active Manager access (403); missing draft returns 404, stale/inactive
     * draft 409 and invalid changes 422. On conflict reread the draft before editing.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
     * @param draftId
     * @param requestBody
     * @returns BotQuickOrderDraftSessionResponse Successful Response
     * @throws ApiError
     */
    public static patchInternalBotQuickOrderDraftV1(
        draftId: string,
        requestBody: BotQuickOrderDraftPatchRequest,
    ): CancelablePromise<BotQuickOrderDraftSessionResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/internal/bot/v1/quick-orders/drafts/{draft_id}',
            path: {
                'draft_id': draftId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Cancel Internal Bot Quick Order Draft
     * Cancel the actor’s active durable draft using expected_version. Requires active Manager
     * access (403); missing draft returns 404, stale or inactive draft 409 and invalid input
     * 422. Cancellation increments version.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
     * @param draftId
     * @param requestBody
     * @returns BotQuickOrderDraftSessionResponse Successful Response
     * @throws ApiError
     */
    public static cancelInternalBotQuickOrderDraftV1(
        draftId: string,
        requestBody: BotQuickOrderDraftActionRequest,
    ): CancelablePromise<BotQuickOrderDraftSessionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/quick-orders/drafts/{draft_id}/cancel',
            path: {
                'draft_id': draftId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Internal Bot Quick Order From Draft
     * Create an order from the Manager actor’s durable draft in the system tenant. Active
     * drafts require expected_version; stale/inactive drafts return 409 and missing drafts
     * 404. A retry after successful creation returns the recorded order/customer with
     * created=false, using a draft-derived idempotency key.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
     * @param draftId
     * @param requestBody
     * @returns BotQuickOrderCreateResponse Successful Response
     * @throws ApiError
     */
    public static createInternalBotQuickOrderFromDraftV1(
        draftId: string,
        requestBody: BotQuickOrderDraftActionRequest,
    ): CancelablePromise<BotQuickOrderCreateResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/quick-orders/drafts/{draft_id}/create',
            path: {
                'draft_id': draftId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Internal Bot Quick Order
     * Create a system-tenant order from a submitted quick-order draft for an active Manager
     * Telegram actor (403 otherwise). Uses the supplied idempotency_key; retain it when
     * repeating the same creation. Service validation errors return 422; inspect created and
     * the returned order/customer IDs.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
     * @param requestBody
     * @returns BotQuickOrderCreateResponse Successful Response
     * @throws ApiError
     */
    public static createInternalBotQuickOrderV1(
        requestBody: BotQuickOrderCreateRequest,
    ): CancelablePromise<BotQuickOrderCreateResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/quick-orders',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Recognize Internal Bot Customer Requisites Text
     * Recognize customer requisites from text for an active Manager Telegram actor in the
     * system tenant. Returns a recognition for explicit follow-up action; OCR alone does not
     * confirm customer creation. Access denial returns 403 and invalid content 422.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
     * @param requestBody
     * @returns BotCustomerRequisitesRecognitionResponse Successful Response
     * @throws ApiError
     */
    public static recognizeInternalBotCustomerRequisitesTextV1(
        requestBody: BotCustomerRequisitesTextRequest,
    ): CancelablePromise<BotCustomerRequisitesRecognitionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/customers/requisites/recognize-text',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Recognize Internal Bot Customer Requisites File
     * Recognize customer requisites from JPG, PNG, WEBP, PDF, DOC or DOCX, at most 10 MB, for
     * an active Manager Telegram actor in the system tenant. Oversize returns 413,
     * invalid/unsupported content 422, denied access 403. Returns a recognition for a later
     * explicit action.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
     * @param formData
     * @returns BotCustomerRequisitesRecognitionResponse Successful Response
     * @throws ApiError
     */
    public static recognizeInternalBotCustomerRequisitesFileV1(
        formData: Body_recognize_internal_bot_customer_requisites_file_v1,
    ): CancelablePromise<BotCustomerRequisitesRecognitionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/customers/requisites/recognize-file',
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Apply Internal Bot Customer Requisites Action
     * Apply the selected action to an existing requisites recognition in the system tenant for
     * its authorized Manager actor. Access denial returns 403, missing recognition 404,
     * conflicting action/state 409 and invalid input 422. Returns recognition, customer and
     * changed so clients can reconcile the action.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
     * @param recognitionId
     * @param requestBody
     * @returns BotCustomerRequisitesActionResponse Successful Response
     * @throws ApiError
     */
    public static applyInternalBotCustomerRequisitesActionV1(
        recognitionId: number,
        requestBody: BotCustomerRequisitesActionRequest,
    ): CancelablePromise<BotCustomerRequisitesActionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/customers/requisites/{recognition_id}/action',
            path: {
                'recognition_id': recognitionId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
