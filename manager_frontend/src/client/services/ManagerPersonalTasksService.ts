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
