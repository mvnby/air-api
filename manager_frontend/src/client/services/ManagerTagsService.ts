/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerTagCreatePayload } from '../models/ManagerTagCreatePayload';
import type { ManagerTagGroupCreatePayload } from '../models/ManagerTagGroupCreatePayload';
import type { ManagerTagGroupResponse } from '../models/ManagerTagGroupResponse';
import type { ManagerTagGroupUpdatePayload } from '../models/ManagerTagGroupUpdatePayload';
import type { ManagerTagOptionResponse } from '../models/ManagerTagOptionResponse';
import type { ManagerTagUpdatePayload } from '../models/ManagerTagUpdatePayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerTagsService {
    /**
     * Get Tag Groups
     * Get all tag groups with their tags.
     * @returns ManagerTagGroupResponse Successful Response
     * @throws ApiError
     */
    public static getManagerTagGroups(): CancelablePromise<Array<ManagerTagGroupResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/tags/groups',
        });
    }
    /**
     * Create Tag Group
     * Create a new tag group.
     * @param requestBody
     * @returns ManagerTagGroupResponse Successful Response
     * @throws ApiError
     */
    public static createManagerTagGroup(
        requestBody: ManagerTagGroupCreatePayload,
    ): CancelablePromise<ManagerTagGroupResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/tags/groups',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Tag Group
     * Update an existing tag group.
     * @param groupId
     * @param requestBody
     * @returns ManagerTagGroupResponse Successful Response
     * @throws ApiError
     */
    public static updateManagerTagGroup(
        groupId: number,
        requestBody: ManagerTagGroupUpdatePayload,
    ): CancelablePromise<ManagerTagGroupResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/tags/groups/{group_id}',
            path: {
                'group_id': groupId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Tag Group
     * Delete a tag group. Restrained if the group has tags.
     * @param groupId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static deleteManagerTagGroup(
        groupId: number,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/tags/groups/{group_id}',
            path: {
                'group_id': groupId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Tag
     * Create a new tag in a group.
     * @param requestBody
     * @returns ManagerTagOptionResponse Successful Response
     * @throws ApiError
     */
    public static createManagerTag(
        requestBody: ManagerTagCreatePayload,
    ): CancelablePromise<ManagerTagOptionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/tags',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Tag
     * Update a tag.
     * @param tagId
     * @param requestBody
     * @returns ManagerTagOptionResponse Successful Response
     * @throws ApiError
     */
    public static updateManagerTag(
        tagId: number,
        requestBody: ManagerTagUpdatePayload,
    ): CancelablePromise<ManagerTagOptionResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/tags/{tag_id}',
            path: {
                'tag_id': tagId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Tag
     * Delete a tag.
     * @param tagId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static deleteManagerTag(
        tagId: number,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/tags/{tag_id}',
            path: {
                'tag_id': tagId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
