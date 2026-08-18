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
     * Create Internal Bot Quick Order
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
     * Recognize customer requisites from JPG, PNG, WEBP, PDF, DOC, or DOCX (up to 10 MB).
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
