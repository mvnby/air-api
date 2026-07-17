/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_apply_internal_bot_repair_nameplate_v1 } from '../models/Body_apply_internal_bot_repair_nameplate_v1';
import type { Body_apply_internal_bot_warranty_nameplate_v1 } from '../models/Body_apply_internal_bot_warranty_nameplate_v1';
import type { Body_attach_internal_bot_order_file_v1 } from '../models/Body_attach_internal_bot_order_file_v1';
import type { Body_recognize_internal_bot_repair_nameplate_v1 } from '../models/Body_recognize_internal_bot_repair_nameplate_v1';
import type { Body_recognize_internal_bot_warranty_nameplate_v1 } from '../models/Body_recognize_internal_bot_warranty_nameplate_v1';
import type { BotNameplateApplyResponse } from '../models/BotNameplateApplyResponse';
import type { BotNameplateRecognitionResponse } from '../models/BotNameplateRecognitionResponse';
import type { BotOrderAttachmentResponse } from '../models/BotOrderAttachmentResponse';
import type { BotOrderListRequest } from '../models/BotOrderListRequest';
import type { BotOrderListResponse } from '../models/BotOrderListResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class InternalBotV1MediaService {
    /**
     * List Recent Orders
     * @param requestBody
     * @returns BotOrderListResponse Successful Response
     * @throws ApiError
     */
    public static listInternalBotRecentOrdersV1(
        requestBody: BotOrderListRequest,
    ): CancelablePromise<BotOrderListResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/orders/recent',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Attach Order File
     * @param orderId
     * @param formData
     * @returns BotOrderAttachmentResponse Successful Response
     * @throws ApiError
     */
    public static attachInternalBotOrderFileV1(
        orderId: number,
        formData: Body_attach_internal_bot_order_file_v1,
    ): CancelablePromise<BotOrderAttachmentResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/orders/{order_id}/attachments',
            path: {
                'order_id': orderId,
            },
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Repair Nameplate Orders
     * @param requestBody
     * @returns BotOrderListResponse Successful Response
     * @throws ApiError
     */
    public static listInternalBotRepairNameplateOrdersV1(
        requestBody: BotOrderListRequest,
    ): CancelablePromise<BotOrderListResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/repair-nameplates/orders',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Recognize Repair Nameplate
     * @param formData
     * @returns BotNameplateRecognitionResponse Successful Response
     * @throws ApiError
     */
    public static recognizeInternalBotRepairNameplateV1(
        formData: Body_recognize_internal_bot_repair_nameplate_v1,
    ): CancelablePromise<BotNameplateRecognitionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/repair-nameplates/recognize',
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Apply Repair Nameplate
     * @param formData
     * @returns BotNameplateApplyResponse Successful Response
     * @throws ApiError
     */
    public static applyInternalBotRepairNameplateV1(
        formData: Body_apply_internal_bot_repair_nameplate_v1,
    ): CancelablePromise<BotNameplateApplyResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/repair-nameplates/apply',
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Warranty Nameplate Orders
     * @param requestBody
     * @returns BotOrderListResponse Successful Response
     * @throws ApiError
     */
    public static listInternalBotWarrantyNameplateOrdersV1(
        requestBody: BotOrderListRequest,
    ): CancelablePromise<BotOrderListResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/warranty-nameplates/orders',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Recognize Warranty Nameplate
     * @param formData
     * @returns BotNameplateRecognitionResponse Successful Response
     * @throws ApiError
     */
    public static recognizeInternalBotWarrantyNameplateV1(
        formData: Body_recognize_internal_bot_warranty_nameplate_v1,
    ): CancelablePromise<BotNameplateRecognitionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/warranty-nameplates/recognize',
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Apply Warranty Nameplate
     * @param formData
     * @returns BotNameplateApplyResponse Successful Response
     * @throws ApiError
     */
    public static applyInternalBotWarrantyNameplateV1(
        formData: Body_apply_internal_bot_warranty_nameplate_v1,
    ): CancelablePromise<BotNameplateApplyResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/internal/bot/v1/warranty-nameplates/apply',
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
