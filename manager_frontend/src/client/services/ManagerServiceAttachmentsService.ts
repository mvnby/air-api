/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_upload_manager_order_attachment } from '../models/Body_upload_manager_order_attachment';
import type { ManagerServiceAttachmentAccessResponse } from '../models/ManagerServiceAttachmentAccessResponse';
import type { ManagerServiceAttachmentItemResponse } from '../models/ManagerServiceAttachmentItemResponse';
import type { ManagerServiceAttachmentListResponse } from '../models/ManagerServiceAttachmentListResponse';
import type { ManagerServiceAttachmentUpdatePayload } from '../models/ManagerServiceAttachmentUpdatePayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerServiceAttachmentsService {
    /**
     * List Manager Order Attachments
     * @param orderId
     * @returns ManagerServiceAttachmentListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerOrderAttachments(
        orderId: number,
    ): CancelablePromise<ManagerServiceAttachmentListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/orders/{order_id}/attachments',
            path: {
                'order_id': orderId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Upload Manager Order Attachment
     * @param orderId
     * @param formData
     * @returns ManagerServiceAttachmentItemResponse Successful Response
     * @throws ApiError
     */
    public static uploadManagerOrderAttachment(
        orderId: number,
        formData: Body_upload_manager_order_attachment,
    ): CancelablePromise<ManagerServiceAttachmentItemResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/attachments',
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
     * List Manager Equipment Attachments
     * @param equipmentId
     * @returns ManagerServiceAttachmentListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerEquipmentAttachments(
        equipmentId: number,
    ): CancelablePromise<ManagerServiceAttachmentListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/equipment/{equipment_id}/attachments',
            path: {
                'equipment_id': equipmentId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Patch Manager Service Attachment
     * @param attachmentId
     * @param requestBody
     * @returns ManagerServiceAttachmentItemResponse Successful Response
     * @throws ApiError
     */
    public static patchManagerServiceAttachment(
        attachmentId: number,
        requestBody: ManagerServiceAttachmentUpdatePayload,
    ): CancelablePromise<ManagerServiceAttachmentItemResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/service-attachments/{attachment_id}',
            path: {
                'attachment_id': attachmentId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Manager Service Attachment
     * @param attachmentId
     * @param orderId
     * @returns void
     * @throws ApiError
     */
    public static deleteManagerServiceAttachment(
        attachmentId: number,
        orderId?: (number | null),
    ): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/service-attachments/{attachment_id}',
            path: {
                'attachment_id': attachmentId,
            },
            query: {
                'order_id': orderId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Manager Service Attachment Access
     * @param attachmentId
     * @param variant
     * @param download
     * @returns ManagerServiceAttachmentAccessResponse Successful Response
     * @throws ApiError
     */
    public static getManagerServiceAttachmentAccess(
        attachmentId: number,
        variant: string = 'original',
        download: boolean = false,
    ): CancelablePromise<ManagerServiceAttachmentAccessResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/service-attachments/{attachment_id}/access',
            path: {
                'attachment_id': attachmentId,
            },
            query: {
                'variant': variant,
                'download': download,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
