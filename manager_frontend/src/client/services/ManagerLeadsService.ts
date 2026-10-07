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
     * Page raw Lead records in the current tenant/storefront using
     * status/source/search/overdue/sort filters; limit is at most 100. Without explicit
     * status, the list selects new/contacted leads even when include_archived=true; archived
     * rows are hidden unless requested. Invalid status/source returns 400; unknown sort falls
     * back to newest first. This is the Lead list, not the unified Order+Lead incoming feed;
     * reading does not mark personal read state.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Create a raw Lead in new state in the current tenant/storefront, retaining
     * contact/source/request/follow-up data without creating a customer/order. Blank request
     * or invalid source/segment returns 400. No caller idempotency receipt is provided:
     * repeating POST can create another Lead.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Patch supplied fields of a raw Lead in the current tenant/storefront and increment its
     * version. Omitted fields remain unchanged; terminal qualified/lost/spam statuses require
     * dedicated commands. Missing Lead returns 404; invalid request/status/source/segment
     * returns 400. This patch does not enforce expected_version or provide a replay receipt,
     * even though it increments version.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Qualify a raw Lead in the current tenant/storefront by explicitly selecting or safely
     * matching/creating a customer and branch, then creating an order and transferring
     * applicable lead data. With an explicit scenario the order enters negotiation; otherwise
     * it remains new_lead. Archived/lost/spam, ambiguous customer matches or invalid
     * branch/scenario return 400; missing Lead 404. An already qualified Lead with its
     * accessible converted order returns that order with order_created=false; no generic
     * caller receipt is supplied.
     *
     * Durable quick incoming requires expected_version; a missing/stale version returns
     * 409 before customer/order mutation. Qualification retains the original source text,
     * source clock, corrected fields, field provenance, wished time and prior-call agreement
     * in incoming_context. These wishes do not create a work stage, booked slot or installer
     * assignment. A saved address is used when no delivery address is provided; a region
     * remains region context, never an invented street address.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Mark a raw Lead in the current tenant/storefront lost or spam, retain/set loss reason,
     * clear the follow-up date and increment version. Missing Lead returns 404; unsupported
     * terminal status returns 400. This command has no expected_version precondition or replay
     * receipt and does not archive a linked customer or delete source data.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
