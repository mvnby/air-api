/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ContractReviewJobResponse } from '../models/ContractReviewJobResponse';
import type { LeadsCounterResponse } from '../models/LeadsCounterResponse';
import type { LeadsInboxListResponse } from '../models/LeadsInboxListResponse';
import type { LeadSource } from '../models/LeadSource';
import type { OriginalEmailAttachmentList } from '../models/OriginalEmailAttachmentList';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerLeadsInboxService {
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
     * scope=active  → new_lead + assessment, sorted by is_new DESC then created_at DESC.
     * scope=archive → canceled.
     * @param scope
     * @param page
     * @param limit
     * @param search
     * @param source
     * @returns LeadsInboxListResponse Successful Response
     * @throws ApiError
     */
    public static getManagerLeadsInbox(
        scope: string = 'active',
        page: number = 1,
        limit: number = 50,
        search?: (string | null),
        source?: (LeadSource | null),
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
            },
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
}
