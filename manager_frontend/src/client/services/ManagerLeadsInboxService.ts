/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ContractReviewJobResponse } from '../models/ContractReviewJobResponse';
import type { EmailLeadLinkPayload } from '../models/EmailLeadLinkPayload';
import type { EmailLeadLinkResult } from '../models/EmailLeadLinkResult';
import type { EmailLeadLinkTarget } from '../models/EmailLeadLinkTarget';
import type { EmailLeadUnlinkResult } from '../models/EmailLeadUnlinkResult';
import type { InboxArchivePayload } from '../models/InboxArchivePayload';
import type { InboxNoAnswerPayload } from '../models/InboxNoAnswerPayload';
import type { InboxReadPayload } from '../models/InboxReadPayload';
import type { InboxTenderPayload } from '../models/InboxTenderPayload';
import type { LeadsCounterResponse } from '../models/LeadsCounterResponse';
import type { LeadsInboxDetailResponse } from '../models/LeadsInboxDetailResponse';
import type { LeadsInboxListResponse } from '../models/LeadsInboxListResponse';
import type { LeadSource } from '../models/LeadSource';
import type { OriginalEmailAttachmentList } from '../models/OriginalEmailAttachmentList';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerLeadsInboxService {
    /**
     * Detail
     * @param leadId
     * @returns LeadsInboxDetailResponse Successful Response
     * @throws ApiError
     */
    public static getManagerRawInboxLead(
        leadId: number,
    ): CancelablePromise<LeadsInboxDetailResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/leads/inbox/raw/{lead_id}',
            path: {
                'lead_id': leadId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Mark Read
     * @param leadId
     * @param requestBody
     * @returns LeadsInboxDetailResponse Successful Response
     * @throws ApiError
     */
    public static setManagerRawInboxLeadRead(
        leadId: number,
        requestBody: InboxReadPayload,
    ): CancelablePromise<LeadsInboxDetailResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/leads/inbox/raw/{lead_id}/read',
            path: {
                'lead_id': leadId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Archive
     * @param leadId
     * @param requestBody
     * @returns LeadsInboxDetailResponse Successful Response
     * @throws ApiError
     */
    public static archiveManagerRawInboxLead(
        leadId: number,
        requestBody: InboxArchivePayload,
    ): CancelablePromise<LeadsInboxDetailResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/leads/inbox/raw/{lead_id}/archive',
            path: {
                'lead_id': leadId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Restore
     * @param leadId
     * @returns LeadsInboxDetailResponse Successful Response
     * @throws ApiError
     */
    public static restoreManagerRawInboxLead(
        leadId: number,
    ): CancelablePromise<LeadsInboxDetailResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/leads/inbox/raw/{lead_id}/restore',
            path: {
                'lead_id': leadId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * No Answer
     * @param leadId
     * @param requestBody
     * @returns LeadsInboxDetailResponse Successful Response
     * @throws ApiError
     */
    public static recordManagerRawInboxLeadNoAnswer(
        leadId: number,
        requestBody: InboxNoAnswerPayload,
    ): CancelablePromise<LeadsInboxDetailResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/leads/inbox/raw/{lead_id}/no-answer',
            path: {
                'lead_id': leadId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Leads Counter
     * Fast counter for the Dashboard / Sidebar badge.
     * Counts only orders with status 'new_lead'.
     * @returns LeadsCounterResponse Successful Response
     * @throws ApiError
     */
    public static getManagerLeadsCounter(): CancelablePromise<LeadsCounterResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/leads/counter',
        });
    }
    /**
     * Get Leads Inbox
     * Unified inbox feed.
     *
     * scope=active  → unlinked, unarchived new_lead incoming records.
     * scope=archive → canceled or linked to an existing order.
     * @param scope
     * @param page
     * @param limit
     * @param search
     * @param source
     * @param unreadOnly
     * @param sort
     * @returns LeadsInboxListResponse Successful Response
     * @throws ApiError
     */
    public static getManagerLeadsInbox(
        scope: string = 'active',
        page: number = 1,
        limit: number = 50,
        search?: (string | null),
        source?: (LeadSource | null),
        unreadOnly: boolean = false,
        sort: 'newest' | 'deadline' = 'newest',
    ): CancelablePromise<LeadsInboxListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/leads/inbox',
            query: {
                'scope': scope,
                'page': page,
                'limit': limit,
                'search': search,
                'source': source,
                'unread_only': unreadOnly,
                'sort': sort,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Inbox Detail
     * @param orderId
     * @returns LeadsInboxDetailResponse Successful Response
     * @throws ApiError
     */
    public static getManagerInboxDetail(
        orderId: number,
    ): CancelablePromise<LeadsInboxDetailResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/leads/inbox/{order_id}',
            path: {
                'order_id': orderId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Set Inbox Read
     * @param orderId
     * @param requestBody
     * @returns LeadsInboxDetailResponse Successful Response
     * @throws ApiError
     */
    public static setManagerInboxRead(
        orderId: number,
        requestBody: InboxReadPayload,
    ): CancelablePromise<LeadsInboxDetailResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/leads/inbox/{order_id}/read',
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
     * Archive Inbox Item
     * @param orderId
     * @param requestBody
     * @returns LeadsInboxDetailResponse Successful Response
     * @throws ApiError
     */
    public static archiveManagerInboxItem(
        orderId: number,
        requestBody: InboxArchivePayload,
    ): CancelablePromise<LeadsInboxDetailResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/leads/inbox/{order_id}/archive',
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
     * Restore Inbox Item
     * @param orderId
     * @returns LeadsInboxDetailResponse Successful Response
     * @throws ApiError
     */
    public static restoreManagerInboxItem(
        orderId: number,
    ): CancelablePromise<LeadsInboxDetailResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/leads/inbox/{order_id}/restore',
            path: {
                'order_id': orderId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Record Inbox No Answer
     * @param orderId
     * @param requestBody
     * @returns LeadsInboxDetailResponse Successful Response
     * @throws ApiError
     */
    public static recordManagerInboxNoAnswer(
        orderId: number,
        requestBody: InboxNoAnswerPayload,
    ): CancelablePromise<LeadsInboxDetailResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/leads/inbox/{order_id}/no-answer',
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
     * Set Inbox Tender
     * @param orderId
     * @param requestBody
     * @returns LeadsInboxDetailResponse Successful Response
     * @throws ApiError
     */
    public static setManagerInboxTender(
        orderId: number,
        requestBody: InboxTenderPayload,
    ): CancelablePromise<LeadsInboxDetailResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/leads/inbox/{order_id}/tender',
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
     * Get Manager Email Lead Contract Review Job
     * @param jobId
     * @returns ContractReviewJobResponse Successful Response
     * @throws ApiError
     */
    public static getManagerEmailLeadContractReviewJob(
        jobId: string,
    ): CancelablePromise<ContractReviewJobResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/leads/inbox/contract-review-jobs/{job_id}',
            path: {
                'job_id': jobId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Manager Email Lead Originals
     * @param orderId
     * @returns OriginalEmailAttachmentList Successful Response
     * @throws ApiError
     */
    public static listManagerEmailLeadOriginals(
        orderId: number,
    ): CancelablePromise<OriginalEmailAttachmentList> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/leads/inbox/{order_id}/email-originals',
            path: {
                'order_id': orderId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Download Manager Email Lead Original
     * @param orderId
     * @param position
     * @returns any Successful Response
     * @throws ApiError
     */
    public static downloadManagerEmailLeadOriginal(
        orderId: number,
        position: number,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/leads/inbox/{order_id}/email-originals/{position}/download',
            path: {
                'order_id': orderId,
                'position': position,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Review Manager Email Lead Original
     * @param orderId
     * @param position
     * @returns ContractReviewJobResponse Successful Response
     * @throws ApiError
     */
    public static reviewManagerEmailLeadOriginal(
        orderId: number,
        position: number,
    ): CancelablePromise<ContractReviewJobResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/leads/inbox/{order_id}/email-originals/{position}/review',
            path: {
                'order_id': orderId,
                'position': position,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Review Manager Email Lead Contract
     * @param orderId
     * @param attachmentId
     * @returns ContractReviewJobResponse Successful Response
     * @throws ApiError
     */
    public static reviewManagerEmailLeadContract(
        orderId: number,
        attachmentId: number,
    ): CancelablePromise<ContractReviewJobResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/leads/inbox/{order_id}/contract-review/{attachment_id}',
            path: {
                'order_id': orderId,
                'attachment_id': attachmentId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Preview Manager Email Lead Link Target
     * @param sourceOrderId
     * @param targetOrderId
     * @returns EmailLeadLinkTarget Successful Response
     * @throws ApiError
     */
    public static previewManagerEmailLeadLinkTarget(
        sourceOrderId: number,
        targetOrderId: number,
    ): CancelablePromise<EmailLeadLinkTarget> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/leads/inbox/{source_order_id}/link-target/{target_order_id}',
            path: {
                'source_order_id': sourceOrderId,
                'target_order_id': targetOrderId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Link Manager Email Lead To Order
     * @param sourceOrderId
     * @param requestBody
     * @returns EmailLeadLinkResult Successful Response
     * @throws ApiError
     */
    public static linkManagerEmailLeadToOrder(
        sourceOrderId: number,
        requestBody: EmailLeadLinkPayload,
    ): CancelablePromise<EmailLeadLinkResult> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/leads/inbox/{source_order_id}/link-to-order',
            path: {
                'source_order_id': sourceOrderId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Unlink Manager Email Lead From Order
     * @param sourceOrderId
     * @returns EmailLeadUnlinkResult Successful Response
     * @throws ApiError
     */
    public static unlinkManagerEmailLeadFromOrder(
        sourceOrderId: number,
    ): CancelablePromise<EmailLeadUnlinkResult> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/leads/inbox/{source_order_id}/linked-order',
            path: {
                'source_order_id': sourceOrderId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
