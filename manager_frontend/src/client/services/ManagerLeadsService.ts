/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { LeadCreatePayload } from '../models/LeadCreatePayload';
import type { LeadListResponse } from '../models/LeadListResponse';
import type { LeadLossPayload } from '../models/LeadLossPayload';
import type { LeadQualifyPayload } from '../models/LeadQualifyPayload';
import type { LeadQualifyResponse } from '../models/LeadQualifyResponse';
import type { LeadResponse } from '../models/LeadResponse';
import type { LeadUpdatePayload } from '../models/LeadUpdatePayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerLeadsService {
    /**
     * Get Manager Leads
     * @param page
     * @param limit
     * @param status
     * @param source
     * @param search
     * @param overdueOnly
     * @param includeArchived
     * @param sort
     * @returns LeadListResponse Successful Response
     * @throws ApiError
     */
    public static getManagerLeads(
        page: number = 1,
        limit: number = 20,
        status?: (string | null),
        source?: (string | null),
        search?: (string | null),
        overdueOnly: boolean = false,
        includeArchived: boolean = false,
        sort: string = 'created_at_desc',
    ): CancelablePromise<LeadListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/leads',
            query: {
                'page': page,
                'limit': limit,
                'status': status,
                'source': source,
                'search': search,
                'overdue_only': overdueOnly,
                'include_archived': includeArchived,
                'sort': sort,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Manager Lead
     * @param requestBody
     * @returns LeadResponse Successful Response
     * @throws ApiError
     */
    public static createManagerLead(
        requestBody: LeadCreatePayload,
    ): CancelablePromise<LeadResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/leads',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Patch Manager Lead
     * @param leadId
     * @param requestBody
     * @returns LeadResponse Successful Response
     * @throws ApiError
     */
    public static patchManagerLead(
        leadId: number,
        requestBody: LeadUpdatePayload,
    ): CancelablePromise<LeadResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/leads/{lead_id}',
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
     * Qualify Manager Lead
     * @param leadId
     * @param requestBody
     * @returns LeadQualifyResponse Successful Response
     * @throws ApiError
     */
    public static qualifyManagerLead(
        leadId: number,
        requestBody: LeadQualifyPayload,
    ): CancelablePromise<LeadQualifyResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/leads/{lead_id}/qualify',
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
     * Mark Manager Lead Lost
     * @param leadId
     * @param requestBody
     * @returns LeadResponse Successful Response
     * @throws ApiError
     */
    public static markManagerLeadLost(
        leadId: number,
        requestBody: LeadLossPayload,
    ): CancelablePromise<LeadResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/leads/{lead_id}/mark-lost',
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
}
