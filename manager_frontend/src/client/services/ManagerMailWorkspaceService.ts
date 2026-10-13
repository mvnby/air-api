/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_upload_manager_mail_draft_attachment } from '../models/Body_upload_manager_mail_draft_attachment';
import type { MailAccountListResponse } from '../models/MailAccountListResponse';
import type { MailConfirmPayload } from '../models/MailConfirmPayload';
import type { MailDraftCreatePayload } from '../models/MailDraftCreatePayload';
import type { MailDraftUpdatePayload } from '../models/MailDraftUpdatePayload';
import type { MailMessageListResponse } from '../models/MailMessageListResponse';
import type { MailMessageResponse } from '../models/MailMessageResponse';
import type { MailVersionPayload } from '../models/MailVersionPayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerMailWorkspaceService {
    /**
     * Mail Accounts
     * List configured mail accounts available to the current company and live staff identity. Partner companies never borrow the platform SMTP account. No credentials are returned.
     * @returns MailAccountListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerMailAccounts(): CancelablePromise<MailAccountListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/mail/accounts',
        });
    }
    /**
     * Mail Messages
     * Search saved company mail in inbox, outbox or drafts; pagination is capped at 100. Linked order/customer filters require access. Inbox IDs are negative to keep one opaque message namespace.
     * @param folder
     * @param q
     * @param status
     * @param orderId
     * @param customerId
     * @param page
     * @param limit
     * @returns MailMessageListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerMailMessages(
        folder: string = 'outbox',
        q?: (string | null),
        status?: (string | null),
        orderId?: (number | null),
        customerId?: (number | null),
        page: number = 1,
        limit: number = 50,
    ): CancelablePromise<MailMessageListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/mail/messages',
            query: {
                'folder': folder,
                'q': q,
                'status': status,
                'order_id': orderId,
                'customer_id': customerId,
                'page': page,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Mail Message
     * Read saved company mail with private attachment download references. Sent/failed/unknown history is immutable; unknown does not authorize a retry. A stale interrupted send is marked unknown.
     * @param messageId
     * @returns MailMessageResponse Successful Response
     * @throws ApiError
     */
    public static getManagerMailMessage(
        messageId: number,
    ): CancelablePromise<MailMessageResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/mail/messages/{message_id}',
            path: {
                'message_id': messageId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Mail Draft
     * Persist an incomplete draft without sending. Order/customer and recipient are optional. Requires a configured account, live staff membership and Idempotency-Key; replay returns the stored result.
     * @param idempotencyKey
     * @param requestBody
     * @returns MailMessageResponse Successful Response
     * @throws ApiError
     */
    public static createManagerMailDraft(
        idempotencyKey: string,
        requestBody: MailDraftCreatePayload,
    ): CancelablePromise<MailMessageResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/mail/drafts',
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Mail Draft
     * Read the current server-saved outgoing message version. Access requires live staff membership and available linked objects.
     * @param draftId
     * @returns MailMessageResponse Successful Response
     * @throws ApiError
     */
    public static getManagerMailDraft(
        draftId: number,
    ): CancelablePromise<MailMessageResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/mail/drafts/{draft_id}',
            path: {
                'draft_id': draftId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Patch Mail Draft
     * Save supplied fields of a draft using expected_version and Idempotency-Key. A conflicting edit returns 409/current_version. Every edit invalidates approval; sent history cannot be edited.
     * @param draftId
     * @param idempotencyKey
     * @param requestBody
     * @returns MailMessageResponse Successful Response
     * @throws ApiError
     */
    public static patchManagerMailDraft(
        draftId: number,
        idempotencyKey: string,
        requestBody: MailDraftUpdatePayload,
    ): CancelablePromise<MailMessageResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/mail/drafts/{draft_id}',
            path: {
                'draft_id': draftId,
            },
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Mail Draft
     * Delete only the current draft and its private files. Requires expected_version and Idempotency-Key. History of sending, sent, failed or unknown messages cannot be deleted.
     * @param draftId
     * @param idempotencyKey
     * @param requestBody
     * @returns MailMessageResponse Successful Response
     * @throws ApiError
     */
    public static deleteManagerMailDraft(
        draftId: number,
        idempotencyKey: string,
        requestBody: MailVersionPayload,
    ): CancelablePromise<MailMessageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/mail/drafts/{draft_id}',
            path: {
                'draft_id': draftId,
            },
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Copy Mail Message
     * Create a new editable draft using the exact stored files of a sent or definitively failed message. Unknown/pending/sending messages and legacy metadata-only attachments require manual verification instead of blind resend.
     * @param messageId
     * @param idempotencyKey
     * @param requestBody
     * @returns MailMessageResponse Successful Response
     * @throws ApiError
     */
    public static copyManagerMailMessage(
        messageId: number,
        idempotencyKey: string,
        requestBody: MailVersionPayload,
    ): CancelablePromise<MailMessageResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/mail/messages/{message_id}/copy',
            path: {
                'message_id': messageId,
            },
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Upload Mail Attachment
     * Save private file bytes on the current draft without sending. At most 10 files, 10 MiB each and 20 MiB total; upload increments version and invalidates approval. Requires Idempotency-Key.
     * @param draftId
     * @param idempotencyKey
     * @param formData
     * @returns MailMessageResponse Successful Response
     * @throws ApiError
     */
    public static uploadManagerMailDraftAttachment(
        draftId: number,
        idempotencyKey: string,
        formData: Body_upload_manager_mail_draft_attachment,
    ): CancelablePromise<MailMessageResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/mail/drafts/{draft_id}/attachments',
            path: {
                'draft_id': draftId,
            },
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Download Mail Attachment
     * Download private immutable attachment bytes after company and message/link checks. Returns no-store/nosniff with attachment disposition; public object paths are never exposed.
     * @param draftId
     * @param attachmentId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static downloadManagerMailAttachment(
        draftId: number,
        attachmentId: number,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/mail/drafts/{draft_id}/attachments/{attachment_id}',
            path: {
                'draft_id': draftId,
                'attachment_id': attachmentId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Mail Attachment
     * Remove a private file only from the current draft, incrementing version and invalidating approval. Requires expected_version and Idempotency-Key; sent files stay immutable.
     * @param draftId
     * @param attachmentId
     * @param expectedVersion
     * @param idempotencyKey
     * @returns MailMessageResponse Successful Response
     * @throws ApiError
     */
    public static deleteManagerMailDraftAttachment(
        draftId: number,
        attachmentId: number,
        expectedVersion: number,
        idempotencyKey: string,
    ): CancelablePromise<MailMessageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/mail/drafts/{draft_id}/attachments/{attachment_id}',
            path: {
                'draft_id': draftId,
                'attachment_id': attachmentId,
            },
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            query: {
                'expected_version': expectedVersion,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Preview Mail Draft
     * Return the full saved sender, all recipients, text, private files and content hash for Manager review. A short-lived CSRF token is bound to this Manager credential; MCP never receives approval authority.
     * @param draftId
     * @returns MailMessageResponse Successful Response
     * @throws ApiError
     */
    public static previewManagerMailDraft(
        draftId: number,
    ): CancelablePromise<MailMessageResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/mail/drafts/{draft_id}/preview',
            path: {
                'draft_id': draftId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Confirm Mail Draft
     * Explicitly approve reviewed content_hash/expected_version as the authenticated Manager actor. Requires preview X-CSRF-Token and X-Kitlane-Mail-Approval: manager-review. Approval does not send and cannot be created by MCP.
     * @param draftId
     * @param idempotencyKey
     * @param requestBody
     * @returns MailMessageResponse Successful Response
     * @throws ApiError
     */
    public static confirmManagerMailDraft(
        draftId: number,
        idempotencyKey: string,
        requestBody: MailConfirmPayload,
    ): CancelablePromise<MailMessageResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/mail/drafts/{draft_id}/confirm',
            path: {
                'draft_id': draftId,
            },
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Send Mail Draft
     * Send the saved, approved exact version once. The committed sending claim fences parallel requests and different keys before SMTP. Sent means SMTP accepted; ambiguous failures return unknown with no blind retry. Requires preview CSRF/approval headers and Idempotency-Key.
     * @param draftId
     * @param idempotencyKey
     * @param requestBody
     * @returns MailMessageResponse Successful Response
     * @throws ApiError
     */
    public static sendManagerMailDraft(
        draftId: number,
        idempotencyKey: string,
        requestBody: MailVersionPayload,
    ): CancelablePromise<MailMessageResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/mail/drafts/{draft_id}/send',
            path: {
                'draft_id': draftId,
            },
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
