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
