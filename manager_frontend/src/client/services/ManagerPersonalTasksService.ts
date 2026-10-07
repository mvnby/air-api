/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PersonalTaskAssigneeListResponse } from '../models/PersonalTaskAssigneeListResponse';
import type { PersonalTaskCreatePayload } from '../models/PersonalTaskCreatePayload';
import type { PersonalTaskListResponse } from '../models/PersonalTaskListResponse';
import type { PersonalTaskResponse } from '../models/PersonalTaskResponse';
import type { PersonalTaskStatusPayload } from '../models/PersonalTaskStatusPayload';
import type { PersonalTaskUpdatePayload } from '../models/PersonalTaskUpdatePayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerPersonalTasksService {
    /**
     * List Manager Personal Tasks
     * List personal tasks in the current tenant/storefront where the authenticated staff member is
     * author or assignee. Requires a staff owner/admin/manager account with no mandatory password
     * change; legacy identities without staff ID return 403. Supports filter and offset
     * pagination, limit 1–100 (default 50), and returns list counters. It is not an all-company
     * task list, even for owners. See [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param filter
     * @param limit
     * @param offset
     * @returns PersonalTaskListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerPersonalTasks(
        filter: 'active' | 'today' | 'overdue' | 'undated' | 'completed' | 'cancelled' = 'active',
        limit: number = 50,
        offset?: number,
    ): CancelablePromise<PersonalTaskListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/personal-tasks',
            query: {
                'filter': filter,
                'limit': limit,
                'offset': offset,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Manager Personal Task
     * Create a personal task in the current tenant/storefront; the authenticated staff member is
     * author and default assignee. Requires a staff owner/admin/manager account without mandatory
     * password change; demo writes return 403. Assignee and related entities must be accessible or
     * return 422. Idempotency-Key is required: the same actor/scope/command/key and payload replay
     * the stored 201 response with Idempotency-Replayed=true; changed payload returns 409
     * idempotency_key_reused, busy receipt storage 503 with Retry-After: 1. Missing header returns
     * 422; malformed key returns 400.
     * @param idempotencyKey
     * @param requestBody
     * @returns PersonalTaskResponse Successful Response
     * @throws ApiError
     */
    public static createManagerPersonalTask(
        idempotencyKey: string,
        requestBody: PersonalTaskCreatePayload,
    ): CancelablePromise<PersonalTaskResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/personal-tasks',
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Manager Personal Task Assignees
     * List active staff with active memberships in the current tenant as task-assignee candidates,
     * up to limit 1–100. Requires a staff owner/admin/manager account with no mandatory password
     * change. This read neither grants storefront access nor assigns a task; candidate membership
     * is validated again by task mutations.
     * @param limit
     * @returns PersonalTaskAssigneeListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerPersonalTaskAssignees(
        limit: number = 100,
    ): CancelablePromise<PersonalTaskAssigneeListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/personal-tasks/assignees',
            query: {
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Manager Personal Task
     * Read a personal task visible to its author or assignee in the current tenant/storefront,
     * including its version and linked entities. Requires a staff owner/admin/manager account with
     * no mandatory password change. Missing or invisible tasks return 404 with
     * detail.code=personal_task_not_found; owner role does not bypass this visibility rule.
     * @param taskId
     * @returns PersonalTaskResponse Successful Response
     * @throws ApiError
     */
    public static getManagerPersonalTask(
        taskId: number,
    ): CancelablePromise<PersonalTaskResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/personal-tasks/{task_id}',
            path: {
                'task_id': taskId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Patch Manager Personal Task
     * Patch supplied task fields using expected_version; the task must be visible to its author or
     * assignee in the current tenant/storefront. Requires a staff owner/admin/manager account
     * without mandatory password change; demo writes return 403. A successful edit increments
     * version. Missing/invisible task returns 404; stale version returns 409
     * personal_task_version_conflict with current_version; invalid links/assignee return 422.
     * Required Idempotency-Key replays the same actor/scoped command and payload with
     * Idempotency-Replayed=true; changed payload returns 409 and busy receipts return 503 with
     * Retry-After: 1. Retry the same command/key before issuing a new edit.
     * @param taskId
     * @param idempotencyKey
     * @param requestBody
     * @returns PersonalTaskResponse Successful Response
     * @throws ApiError
     */
    public static patchManagerPersonalTask(
        taskId: number,
        idempotencyKey: string,
        requestBody: PersonalTaskUpdatePayload,
    ): CancelablePromise<PersonalTaskResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/personal-tasks/{task_id}',
            path: {
                'task_id': taskId,
            },
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Handler
     * Complete an active task visible to its author or assignee in the current tenant/storefront. Requires a staff owner/admin/manager account without mandatory password change; demo writes return 403. Supply expected_version and Idempotency-Key. Success sets completed status/time and increments version. Missing/invisible task returns 404; stale version or non-active status returns 409 with a specific detail.code. The same actor/scoped command/key and payload replay the stored response with Idempotency-Replayed=true; changed payload returns 409 idempotency_key_reused, busy receipts 503 with Retry-After: 1. A new key after completion is a new command and conflicts with the completed status.
     * @param taskId
     * @param idempotencyKey
     * @param requestBody
     * @returns PersonalTaskResponse Successful Response
     * @throws ApiError
     */
    public static completeManagerPersonalTask(
        taskId: number,
        idempotencyKey: string,
        requestBody: PersonalTaskStatusPayload,
    ): CancelablePromise<PersonalTaskResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/personal-tasks/{task_id}/complete',
            path: {
                'task_id': taskId,
            },
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Handler
     * Reopen a completed or cancelled task visible to its author or assignee in the current tenant/storefront. Requires a staff owner/admin/manager account without mandatory password change; demo writes return 403. Supply expected_version and Idempotency-Key. Success sets active status, clears completion/cancellation timestamps and increments version. Missing/invisible task returns 404; stale version or already-active status returns 409. The same actor/scoped command/key and payload replay the stored response with Idempotency-Replayed=true; changed payload returns 409 idempotency_key_reused and busy receipts return 503 with Retry-After: 1. A new key does not replay the previous reopen.
     * @param taskId
     * @param idempotencyKey
     * @param requestBody
     * @returns PersonalTaskResponse Successful Response
     * @throws ApiError
     */
    public static reopenManagerPersonalTask(
        taskId: number,
        idempotencyKey: string,
        requestBody: PersonalTaskStatusPayload,
    ): CancelablePromise<PersonalTaskResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/personal-tasks/{task_id}/reopen',
            path: {
                'task_id': taskId,
            },
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Handler
     * Cancel an active task visible to its author or assignee in the current tenant/storefront. Requires a staff owner/admin/manager account without mandatory password change; demo writes return 403. Supply expected_version and Idempotency-Key. Success sets cancelled status/time and increments version; the task is retained and can be reopened. Missing/invisible task returns 404; stale version or non-active status returns 409. The same actor/scoped command/key and payload replay the stored response with Idempotency-Replayed=true; changed payload returns 409 idempotency_key_reused and busy receipts return 503 with Retry-After: 1. A new key after cancellation is a new command and conflicts.
     * @param taskId
     * @param idempotencyKey
     * @param requestBody
     * @returns PersonalTaskResponse Successful Response
     * @throws ApiError
     */
    public static cancelManagerPersonalTask(
        taskId: number,
        idempotencyKey: string,
        requestBody: PersonalTaskStatusPayload,
    ): CancelablePromise<PersonalTaskResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/personal-tasks/{task_id}/cancel',
            path: {
                'task_id': taskId,
            },
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
