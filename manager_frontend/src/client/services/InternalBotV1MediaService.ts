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
     * List recent system-tenant orders for an active Manager Telegram actor (403 otherwise).
     * Uses the requested response bound; it is not a storefront catalog or a general tenant
     * selector.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
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
     * Attach a nonempty file (at most 10 MB) to an accessible system-tenant order. Requires
     * active staff; Managers can attach beyond their own assigned execution. Access denial
     * returns 403 and unavailable order 404. Empty/oversize uploads return 422/413. file_id
     * deduplicates attachments; inspect already_attached.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
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
     * List repair orders in the system tenant available to the staff actor under repair-order
     * access rules. Managers may access beyond assigned execution; non-staff return 403.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
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
     * Recognize an equipment nameplate for a repair order accessible to the staff actor in the
     * system tenant. Does not apply the recognized data. Non-staff return 403, unavailable
     * order 404, empty/oversize upload 422/413; file must be at most 10 MB.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
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
     * Apply submitted recognition data and attach its file to an accessible repair order in
     * the system tenant. Requires active staff with order access (403/404 otherwise).
     * extracted_json and validation_json must be JSON objects; invalid JSON/empty file returns
     * 422 and file above 10 MB returns 413. Telegram file_id participates in attachment
     * reconciliation.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
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
     * List warranty orders available to the staff actor in the system tenant and return the
     * service’s execution/Manager scope marker. Non-staff return 403; access is checked before
     * listing.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
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
     * Recognize the selected indoor/outdoor unit nameplate for an accessible warranty order in
     * the system tenant, without applying it. Requires active staff (403); unavailable order
     * returns 404. Empty/oversize upload returns 422/413; file must be at most 10 MB.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
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
     * Apply submitted indoor/outdoor nameplate data and attach its file to an accessible
     * warranty order in the system tenant. Requires active staff (403); unavailable order
     * returns 404. JSON object parsing and empty file validation return 422; file above 10 MB
     * returns 413. Telegram file_id is passed to the attachment workflow.
     *
     * Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
     * checks are separate. See [bot
     * boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
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
