/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OrderUsageAccepted } from '../models/OrderUsageAccepted';
import type { OrderUsageBatch } from '../models/OrderUsageBatch';
import type { OrderUsageReport } from '../models/OrderUsageReport';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerOrderUsageService {
    /**
     * Record Manager Order Usage
     * Add a bounded batch of order-workspace UX aggregate events in the current
     * tenant/storefront. Manager access is required. Aggregates contain permitted event labels
     * rather than customer/order field content. In-process rate/concurrency protection returns
     * 429 with Retry-After. This is additive and has no replay receipt: blindly retrying can
     * double-count. See [usage
     * boundaries](https://github.com/mvnby/air-api/blob/main/docs/order-workspace-usability.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param requestBody
     * @returns OrderUsageAccepted Successful Response
     * @throws ApiError
     */
    public static recordManagerOrderUsage(
        requestBody: OrderUsageBatch,
    ): CancelablePromise<OrderUsageAccepted> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/order-workspace-usage/batch',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Manager Order Usage
     * Read daily aggregate UX counts for the current tenant/storefront over 1–90 days and
     * optional workflow/party/viewport filters. Requires owner/admin access via route policy.
     * Returns aggregated counters, not individual employee click histories. See [usage
     * boundaries](https://github.com/mvnby/air-api/blob/main/docs/order-workspace-usability.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param days
     * @param workflow
     * @param partyKind
     * @param viewport
     * @returns OrderUsageReport Successful Response
     * @throws ApiError
     */
    public static getManagerOrderUsage(
        days: number = 30,
        workflow?: ('sales_installation' | 'work' | 'maintenance' | 'repair' | null),
        partyKind?: ('individual' | 'individual_entrepreneur' | 'company' | 'unknown' | null),
        viewport?: ('mobile' | 'tablet' | 'desktop' | null),
    ): CancelablePromise<OrderUsageReport> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/order-workspace-usage/daily',
            query: {
                'days': days,
                'workflow': workflow,
                'party_kind': partyKind,
                'viewport': viewport,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
