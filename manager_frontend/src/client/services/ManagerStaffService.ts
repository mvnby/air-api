/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerStaffCreatePayload } from '../models/ManagerStaffCreatePayload';
import type { ManagerStaffListResponse } from '../models/ManagerStaffListResponse';
import type { ManagerStaffResponse } from '../models/ManagerStaffResponse';
import type { ManagerStaffUpdatePayload } from '../models/ManagerStaffUpdatePayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerStaffService {
    /**
     * List Staff
     * List staff memberships in the current tenant for an owner/admin. Supports search and
     * page-based pagination with limit 1–100 (default 100). Returned roles/status reflect the
     * tenant membership; account profile and credential-presence flags are included, not password
     * hashes. Does not provision accounts or memberships.
     * @param page
     * @param limit
     * @param search
     * @returns ManagerStaffListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerStaff(
        page: number = 1,
        limit: number = 100,
        search?: (string | null),
    ): CancelablePromise<ManagerStaffListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/staff',
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
     * Create Staff
     * Create a staff identity and membership in the current tenant, optionally with password,
     * Telegram identity and installer linkage. Requires a current-tenant owner/admin. The service
     * hashes a supplied password, synchronizes the installer link when applicable and commits both
     * identity and membership. Invalid values or duplicate login/Telegram ID return 400. No
     * Idempotency-Key receipt makes a repeated create safe.
     * @param requestBody
     * @returns ManagerStaffResponse Successful Response
     * @throws ApiError
     */
    public static createManagerStaff(
        requestBody: ManagerStaffCreatePayload,
    ): CancelablePromise<ManagerStaffResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/staff',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Patch Staff
     * Patch a staff member reached through the current tenant membership; requires an owner/admin.
     * Only supplied fields are changed. Role/status affect the membership, while permitted
     * identity fields affect the shared account; non-system tenants cannot change protected
     * shared-profile fields for multi-tenant staff. A new password increments auth_version.
     * Missing membership returns 404, invalid/duplicate values 400 and protected legacy-owner
     * identity mutation 409 with code/message. There is no optimistic version or replay receipt.
     * @param staffUserId
     * @param requestBody
     * @returns ManagerStaffResponse Successful Response
     * @throws ApiError
     */
    public static patchManagerStaff(
        staffUserId: number,
        requestBody: ManagerStaffUpdatePayload,
    ): CancelablePromise<ManagerStaffResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/staff/{staff_user_id}',
            path: {
                'staff_user_id': staffUserId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
