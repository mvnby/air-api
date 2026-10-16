/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_manager_upload_own_avatar } from '../models/Body_manager_upload_own_avatar';
import type { ManagerOwnAvatarDelete } from '../models/ManagerOwnAvatarDelete';
import type { ManagerOwnProfileResponse } from '../models/ManagerOwnProfileResponse';
import type { ManagerOwnProfileUpdate } from '../models/ManagerOwnProfileUpdate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerProfileService {
    /**
     * Get Own Profile
     * Read only the authenticated person's contact, avatar and Telegram settings.
     * @returns ManagerOwnProfileResponse Successful Response
     * @throws ApiError
     */
    public static managerGetOwnProfile(): CancelablePromise<ManagerOwnProfileResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/account/profile',
        });
    }
    /**
     * Update Own Profile
     * Change whitelisted personal fields with an optimistic timestamp and atomic audit.
     *
     * Company roles, grants, credentials and Telegram bindings cannot be set here.
     * Requires X-Kitlane-Profile: 1. A stale timestamp returns 409/profile_changed.
     * @param requestBody
     * @returns ManagerOwnProfileResponse Successful Response
     * @throws ApiError
     */
    public static managerUpdateOwnProfile(
        requestBody: ManagerOwnProfileUpdate,
    ): CancelablePromise<ManagerOwnProfileResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/account/profile',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Upload Own Avatar
     * Replace your photo with a sanitized 256px WebP; JPEG/PNG/WebP up to 5 MiB.
     *
     * Requires X-Kitlane-Profile: 1 and the current profile timestamp. Image processing
     * discards metadata, rejects animation and runs outside the async event loop.
     * @param formData
     * @returns ManagerOwnProfileResponse Successful Response
     * @throws ApiError
     */
    public static managerUploadOwnAvatar(
        formData: Body_manager_upload_own_avatar,
    ): CancelablePromise<ManagerOwnProfileResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/account/profile/avatar',
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Own Avatar
     * Remove your photo, checking the current timestamp and recording an audit event.
     * @param requestBody
     * @returns ManagerOwnProfileResponse Successful Response
     * @throws ApiError
     */
    public static managerDeleteOwnAvatar(
        requestBody: ManagerOwnAvatarDelete,
    ): CancelablePromise<ManagerOwnProfileResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/account/profile/avatar',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Read Staff Avatar
     * Read a coworker's photo after company access checks, including before a 304.
     *
     * Historical memberships retain photo visibility on old orders. Platform owners
     * can read across companies. Photos are private and revalidated on every request.
     * @param staffUserId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static managerReadStaffAvatar(
        staffUserId: number,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/staff/{staff_user_id}/avatar',
            path: {
                'staff_user_id': staffUserId,
            },
            errors: {
                304: `Not Modified`,
                404: `Not Found`,
                422: `Validation Error`,
            },
        });
    }
}
