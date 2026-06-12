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
