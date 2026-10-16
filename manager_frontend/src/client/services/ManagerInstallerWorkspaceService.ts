/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerCollectionUpdate } from '../models/ManagerCollectionUpdate';
import type { ManagerInstallerWorkspace } from '../models/ManagerInstallerWorkspace';
import type { WorkerAssignmentCreate } from '../models/WorkerAssignmentCreate';
import type { WorkerAssignmentPublicationUpdate } from '../models/WorkerAssignmentPublicationUpdate';
import type { WorkerAssignmentRevoke } from '../models/WorkerAssignmentRevoke';
import type { WorkerCandidatesResponse } from '../models/WorkerCandidatesResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerInstallerWorkspaceService {
    /**
     * Candidates
     * Page active actual company owner/admin/manager/installer assignment candidates.
     *
     * Requires CRM access; virtual support is allowed to manage a partner, but does not
     * become a candidate without actual membership. No credentials/payroll are returned.
     * @param page
     * @param limit
     * @returns WorkerCandidatesResponse Successful Response
     * @throws ApiError
     */
    public static listManagerWorkerCandidates(
        page: number = 1,
        limit: number = 100,
    ): CancelablePromise<WorkerCandidatesResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/worker-candidates',
            query: {
                'page': page,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Workspace
     * Read scoped work grants, approved publications and the current collection review state.
     *
     * CRM membership or verified platform support is required. A foreign/missing order
     * returns404. Financial balances/fingerprint are Manager-only and do not create or
     * repair any proposal, assignment, payment or worker profile.
     * @param orderId
     * @returns ManagerInstallerWorkspace Successful Response
     * @throws ApiError
     */
    public static getManagerInstallerWorkspace(
        orderId: number,
    ): CancelablePromise<ManagerInstallerWorkspace> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/orders/{order_id}/installer-workspace',
            path: {
                'order_id': orderId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Assignment
     * Explicitly assign an actual company worker to an order or active visit.
     *
     * Requires X-Kitlane-Team:1 and approved Origin. Fresh authority/eligibility and scope
     * are checked under ordered locks. Creates a company worker profile if needed;
     * does not copy internal comments, grant CRM or create payroll/payment records.
     * Assignment and audit commit atomically; duplicate active assignments are reused.
     * @param orderId
     * @param requestBody
     * @returns ManagerInstallerWorkspace Successful Response
     * @throws ApiError
     */
    public static createManagerWorkerAssignment(
        orderId: number,
        requestBody: WorkerAssignmentCreate,
    ): CancelablePromise<ManagerInstallerWorkspace> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/installer-workspace/assignments',
            path: {
                'order_id': orderId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Publish Assignment
     * Publish only explicitly approved work title/instructions and technical attachment links.
     *
     * Requires team Origin/header protection and fresh scoped CRM authority. A stale
     * assignment version returns409; unavailable/nontechnical/foreign materials are
     * rejected. Version, publications and audit are atomic, preserving unrelated order
     * fields and financial data.
     * @param orderId
     * @param assignmentId
     * @param requestBody
     * @returns ManagerInstallerWorkspace Successful Response
     * @throws ApiError
     */
    public static publishManagerWorkerAssignment(
        orderId: number,
        assignmentId: number,
        requestBody: WorkerAssignmentPublicationUpdate,
    ): CancelablePromise<ManagerInstallerWorkspace> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/orders/{order_id}/installer-workspace/assignments/{assignment_id}',
            path: {
                'order_id': orderId,
                'assignment_id': assignmentId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Revoke Assignment
     * Revoke versioned work access with atomic audit; preserve payroll/history and files.
     *
     * Requires team Origin/header protection and fresh scoped CRM authority. Stale
     * versions return409. New reads, downloads and old bot actions lose authorization;
     * the original assignment identity is never reassigned to a different person.
     * @param orderId
     * @param assignmentId
     * @param requestBody
     * @returns ManagerInstallerWorkspace Successful Response
     * @throws ApiError
     */
    public static revokeManagerWorkerAssignment(
        orderId: number,
        assignmentId: number,
        requestBody: WorkerAssignmentRevoke,
    ): CancelablePromise<ManagerInstallerWorkspace> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/installer-workspace/assignments/{assignment_id}/revoke',
            path: {
                'order_id': orderId,
                'assignment_id': assignmentId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Collection
     * Publish/clear one versioned collection instruction to one assigned recipient.
     *
     * Requires team Origin/header protection, live CRM authority, an unchanged financial
     * fingerprint and exact nonnegative money no greater than the current balance in
     * the supported currency. Zero is explicit; null clears. Stale edits return409.
     * This is not confirmation of receipt and never inserts/changes payments or payroll.
     * @param orderId
     * @param requestBody
     * @returns ManagerInstallerWorkspace Successful Response
     * @throws ApiError
     */
    public static putManagerWorkerCollection(
        orderId: number,
        requestBody: ManagerCollectionUpdate,
    ): CancelablePromise<ManagerInstallerWorkspace> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/orders/{order_id}/installer-workspace/collection',
            path: {
                'order_id': orderId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
