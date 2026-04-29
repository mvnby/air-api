/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { LeadsCounterResponse } from '../models/LeadsCounterResponse';
import type { LeadsInboxListResponse } from '../models/LeadsInboxListResponse';
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
     * @returns LeadsInboxListResponse Successful Response
     * @throws ApiError
     */
    public static getManagerLeadsInbox(
        scope: string = 'active',
        page: number = 1,
        limit: number = 50,
    ): CancelablePromise<LeadsInboxListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/leads/inbox',
            query: {
                'scope': scope,
                'page': page,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
