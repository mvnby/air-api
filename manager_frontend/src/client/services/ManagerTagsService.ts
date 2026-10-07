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
     * Read all shared tag groups with their tags; no pagination is accepted. This endpoint
     * does not filter by authenticated storefront.
     *
     * Access and scope: Manager access is required; this reads the shared platform catalog,
     * not tenant-owned copies. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Create a shared tag group, deriving slug from title when omitted. Duplicate slug returns
     * 400. POST has no idempotency receipt; this creates dictionary state rather than
     * assigning product tags.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Update submitted tag-group fields. Missing group returns 404; a slug used by another
     * group returns 400. This edits the shared dictionary, leaving product-tag associations
     * attached to their tag IDs.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Permanently delete an empty shared tag group. Missing group returns 404, including after
     * deletion; any remaining tag blocks deletion with 400. Remove/reassign tags first.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Create a tag in an existing shared group, deriving slug from title when omitted. Missing
     * group returns 404; duplicate slug returns 400. This does not assign the tag to products;
     * POST has no idempotency receipt.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Update submitted tag fields. Missing tag returns 404; conflicting slug returns 400.
     * Product links continue to refer to the same tag ID; editing this shared tag affects all
     * linked products.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Permanently delete the tag and its product-tag links. Missing tag returns 404, including
     * on a repeat after deletion. This removes the shared label rather than just removing it
     * from one product.
     *
     * Access and scope: system-tenant Manager access is required; this operates on the shared
     * platform catalog. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
