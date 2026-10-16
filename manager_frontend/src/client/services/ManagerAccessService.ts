/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerAccessItem } from '../models/ManagerAccessItem';
import type { ManagerAccessList } from '../models/ManagerAccessList';
import type { ManagerAccessUpdate } from '../models/ManagerAccessUpdate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerAccessService {
    /**
     * List Manager Access
     * List company memberships and delegated catalog permissions for the platform owner.
     *
     * Read-only, paginated directory across companies; includes names, roles and status,
     * never credentials or order data. Company owners/admins receive 403.
     * @param page
     * @param limit
     * @param search
     * @returns ManagerAccessList Successful Response
     * @throws ApiError
     */
    public static listManagerAccess(
        page: number = 1,
        limit: number = 50,
        search?: (string | null),
    ): CancelablePromise<ManagerAccessList> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/platform/access',
            query: {
                'page': page,
                'limit': limit,
                'search': search,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Manager Access
     * Replace explicit catalog edit/delete grants for one company membership.
     *
     * Only the platform owner may delegate or revoke; no platform-owner grant is accepted.
     * Live membership/identity status still applies on every use. Changes are audited.
     * Requires expected_updated_at; concurrent changes return 409, missing membership 404.
     * Re-read before retrying a stale request. An unchanged current request is a no-op.
     * @param membershipId
     * @param requestBody
     * @returns ManagerAccessItem Successful Response
     * @throws ApiError
     */
    public static updateManagerAccess(
        membershipId: number,
        requestBody: ManagerAccessUpdate,
    ): CancelablePromise<ManagerAccessItem> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/platform/access/{membership_id}',
            path: {
                'membership_id': membershipId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
