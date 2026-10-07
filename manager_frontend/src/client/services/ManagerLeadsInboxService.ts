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
     * Read a raw unqualified Lead incoming card in the current tenant/storefront, including
     * original intake text, personal read state, contact attempts and up to 100 latest history
     * events. Uses Lead ID, not Order ID; missing/converted/qualified card returns 404. GET
     * does not mark read. See the [incoming triage
     * contract](https://github.com/mvnby/air-api/blob/main/docs/incoming-triage-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Set the current username’s personal read/unread state on a raw unqualified Lead in the
     * current tenant/storefront. Does not qualify or archive it; other users’ read state is
     * independent. Missing/converted card returns 404 and demo mutation 403. Repeating
     * read=true refreshes its read timestamp; no command replay receipt is supplied. See the
     * [incoming triage
     * contract](https://github.com/mvnby/air-api/blob/main/docs/incoming-triage-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Archive a raw unqualified Lead incoming card in the current tenant/storefront with
     * shared outcome/reason/note/author history, retaining original data and incrementing its
     * intake version. Does not create/archive a customer. Missing/converted card returns 404,
     * already archived 409 and demo mutation 403. Repeating POST conflicts rather than
     * replaying a receipt. See the [incoming triage
     * contract](https://github.com/mvnby/air-api/blob/main/docs/incoming-triage-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Restore an archived raw Lead in the current tenant/storefront to new state, clear
     * current loss/archive markers and increment version, preserving the previous decision in
     * history. Missing/converted card returns 404, already active 409 and demo mutation 403.
     * This does not undo a qualification or restore a customer. See the [incoming triage
     * contract](https://github.com/mvnby/air-api/blob/main/docs/incoming-triage-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Add a contact-attempt event to an active raw Lead in the current tenant/storefront, set
     * contacted status and increment intake version. Supplied next_followup_at sets/clears the
     * reminder; omission retains it. Missing/converted card returns 404, archive state 409 and
     * demo mutation 403. Repeating POST adds another attempt; no replay receipt is supplied.
     * See the [incoming triage
     * contract](https://github.com/mvnby/air-api/blob/main/docs/incoming-triage-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Count active incoming Order records and unqualified raw Leads accessible in the current
     * tenant/storefront. count/unread_count are the current username’s personal unread count;
     * pending_count includes all active pending records regardless of read state. Reading does
     * not mark records read. See the [incoming triage
     * contract](https://github.com/mvnby/air-api/blob/main/docs/incoming-triage-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Page the unified incoming queue in the current tenant/storefront, merging Order and raw
     * Lead records after search/source/unread filters and sorting. entity_kind distinguishes
     * IDs that can overlap. Active excludes linked/archived/processed records; archive
     * includes retained decisions, linked emails and legacy losses. limit is at most 100; read
     * state is personal while decisions are shared. Does not mark records read. See the
     * [incoming triage
     * contract](https://github.com/mvnby/air-api/blob/main/docs/incoming-triage-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Read an Order-based incoming card accessible in the current tenant/storefront, including
     * original email text, personal read state and up to 100 latest triage events. Arbitrary
     * qualified orders are not exposed through this endpoint; missing/ineligible card returns
     * 404. GET itself does not mark read; use the read command. See the [incoming triage
     * contract](https://github.com/mvnby/air-api/blob/main/docs/incoming-triage-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Set the current username’s personal read/unread state for an accessible Order-based
     * incoming card in the current tenant/storefront. Does not accept/archive the request or
     * alter another manager’s read state. Missing card returns 404, already processed state
     * 409 and demo mutation 403. Repeating the same state preserves the original read
     * timestamp while marked read. See the [incoming triage
     * contract](https://github.com/mvnby/air-api/blob/main/docs/incoming-triage-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Archive an active unlinked Order-based incoming card in the current tenant/storefront
     * with outcome/reason/note and a shared author/time event. Retains source and customer;
     * does not close the business order or archive the customer. Missing card returns 404,
     * already processed/archived/linked state 409 and demo mutation 403. Repeat is a state
     * conflict rather than idempotency receipt replay. See the [incoming triage
     * contract](https://github.com/mvnby/air-api/blob/main/docs/incoming-triage-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Restore an archived Order-based incoming card in the current tenant/storefront,
     * retaining the prior decision in history. Legacy closed-lost incoming records return to
     * new_lead; a linked email must be unlinked first. Suppresses repeat automatic expiry for
     * the same deadline. Missing card returns 404, already active/linked/processed state 409
     * and demo mutation 403. See the [incoming triage
     * contract](https://github.com/mvnby/air-api/blob/main/docs/incoming-triage-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Record an additional contact attempt on an active unlinked Order-based incoming card in
     * the current tenant/storefront. Supplied next_followup_at sets or clears the reminder;
     * omission retains it. Does not archive or accept the card. Missing card returns 404,
     * processed/archive state 409 and demo mutation 403. Each POST adds an event; no replay
     * receipt prevents duplicate attempts. See the [incoming triage
     * contract](https://github.com/mvnby/air-api/blob/main/docs/incoming-triage-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Explicitly confirm an active email incoming card as a tender or ordinary request in the
     * current tenant/storefront, storing actor/time and a triage event. Submitted
     * deadline/source URL are retained only for tenders; omitted values preserve previous
     * context. This is source classification, not a work schedule; it can affect
     * deadline-autoarchive eligibility. Missing card returns 404, non-email/processed/archive
     * state 409 and demo mutation 403. No replay receipt suppresses repeated history events.
     * See the [incoming triage
     * contract](https://github.com/mvnby/air-api/blob/main/docs/incoming-triage-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Poll an AI review job owned by the authenticated tenant+username. Returns
     * running/completed/failed with report or sanitized error; does not start a new review.
     * Jobs live only in the serving process; a finished job expires 30 minutes after creation,
     * and restart/another process can lose it. Unknown, foreign-owner or expired job returns
     * 404. See the [incoming triage
     * contract](https://github.com/mvnby/air-api/blob/main/docs/incoming-triage-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * List attachment positions/names/types/sizes from the original mailbox message for an
     * email-source order accessible in the current tenant/storefront. Reads the retained email
     * source, not just copied private attachments. Missing source/message returns 404; mailbox
     * loading failure 503. Does not invoke AI or mark the incoming card read.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Download one position from the original mailbox message for an email-source order
     * accessible in the current tenant/storefront. Returns private/no-store
     * application/octet-stream attachment. Missing source/position returns 404; mailbox
     * loading failure 503. Original retention/availability is required; this does not create
     * an order attachment.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Start an explicit background AI contract review of a mailbox-original attachment from an
     * accessible scoped email order. Requires system-tenant Manager access. Returns a running
     * job owned by tenant+username; poll its result rather than treating HTTP success as a
     * completed report. Missing original/position returns 404, mailbox failure 503, per-actor
     * limiter 429 with Retry-After or process-capacity refusal 429.
     * Unsupported/unreadable/oversized contract may fail inside the job. No replay receipt:
     * repeat POST can launch another job. See the [incoming triage
     * contract](https://github.com/mvnby/air-api/blob/main/docs/incoming-triage-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Start an explicit background AI contract review of a saved original email attachment
     * linked to an accessible order in the current tenant/storefront. Requires system-tenant
     * Manager access. Returns a tenant+username-owned running job, not a completed report;
     * document/provider validation failures can appear as failed job state. Missing
     * attachment/context returns 404; per-actor limiter 429 with Retry-After and process
     * capacity 429. No generic idempotency key is supplied. See the [incoming triage
     * contract](https://github.com/mvnby/air-api/blob/main/docs/incoming-triage-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Preview the selected existing order as a link target for an accessible email new_lead in
     * the current tenant/storefront. Does not link, copy attachments or run the full
     * unworked-source checks used by commit. Missing source/target returns 404,
     * invalid/self/new-lead target 422 and another existing link 409. See the [incoming triage
     * contract](https://github.com/mvnby/air-api/blob/main/docs/incoming-triage-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Link an unworked email new_lead to an existing accessible order in the current
     * tenant/storefront, recording actor/time and mirroring private attachment links while
     * retaining the source. Paid or previously sent sources are rejected (422); missing
     * context returns 404, different existing link 409 and unavailable needed mailbox original
     * 503. Same target can reuse the existing link result; no caller replay key is supplied.
     * The target may be closed. See the [incoming triage
     * contract](https://github.com/mvnby/air-api/blob/main/docs/incoming-triage-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Remove an accessible email lead’s link in the current tenant/storefront and archive only
     * attachment links mirrored from that source into the target. Source files and target
     * business record remain. Returns the former target ID; missing source/link returns 404,
     * including repeated unlink. Does not delete original attachments or restore a separate
     * manual archive decision. See the [incoming triage
     * contract](https://github.com/mvnby/air-api/blob/main/docs/incoming-triage-workspace.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
