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
     * Read active attachment links for a scoped order with their category, caption and
     * equipment/service context. Missing or inaccessible order returns 404; no pagination
     * parameters are accepted. This returns metadata rather than file bytes or permanent
     * public URLs.
     *
     * Access and scope: Manager access is required; the order and its children are restricted
     * to the authenticated tenant and selected storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [private service
     * attachments](https://github.com/mvnby/air-api/blob/main/docs/service-attachments.md).
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
     * Upload a private attachment and create its order link, optionally also linking validated
     * work stage, equipment, component or service history. Empty/oversized files, unsupported
     * type/category and invalid target relationships return 400. Image previews are generated
     * during ingestion when supported; identical bytes may reuse storage while ordinary manual
     * uploads still create separate attachment occurrences. No idempotency receipt is
     * required.
     *
     * Access and scope: Manager access is required; the order and its children are restricted
     * to the authenticated tenant and selected storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [private service
     * attachments](https://github.com/mvnby/air-api/blob/main/docs/service-attachments.md).
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
     * Read active private attachment links associated with customer equipment. Missing or
     * inaccessible equipment returns 404; no pagination parameters are accepted. Attachment
     * access remains subject to active link ownership; this does not publish files into the
     * general media library.
     *
     * Access and scope: Manager access is required; equipment ownership is inherited from its
     * customer in the authenticated tenant. Linked orders must also belong to the selected
     * storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [private service
     * attachments](https://github.com/mvnby/air-api/blob/main/docs/service-attachments.md).
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
     * Update attachment/link metadata without replacing its file bytes. order_id is required
     * to change category, caption or equipment/component/history association; missing context
     * or invalid relationships returns 400. Missing/archived or inaccessible attachment
     * returns 404. Shared metadata changes require all active links to be owned by the
     * caller’s scope; per-order link edits update the corresponding equipment context.
     *
     * Access and scope: Manager access is required; active attachment links must pass order
     * tenant/storefront or equipment customer-tenant ownership checks. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [private service
     * attachments](https://github.com/mvnby/air-api/blob/main/docs/service-attachments.md).
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
     * Archive an attachment’s link to the specified order and its derived equipment links,
     * returning 204. Without order_id all active links must be owned by the caller before
     * archival; the attachment is archived only when no active links remain. File bytes are
     * retained. Missing/inaccessible/already archived attachment or link returns 404,
     * including repeats.
     *
     * Access and scope: Manager access is required; active attachment links must pass order
     * tenant/storefront or equipment customer-tenant ownership checks. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [private service
     * attachments](https://github.com/mvnby/air-api/blob/main/docs/service-attachments.md).
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
     * Issue a short-lived access URL for an active private attachment after ownership checks,
     * optionally for download. Requested preview falls back to original when no preview
     * exists; the returned variant identifies the actual file. URL expiry is configured
     * between 30 and 3600 seconds. Missing/inaccessible attachment or source returns 404. The
     * returned URL grants temporary file access; this does not create a permanent public media
     * URL.
     *
     * Access and scope: Manager access is required; active attachment links must pass order
     * tenant/storefront or equipment customer-tenant ownership checks. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [private service
     * attachments](https://github.com/mvnby/air-api/blob/main/docs/service-attachments.md).
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
