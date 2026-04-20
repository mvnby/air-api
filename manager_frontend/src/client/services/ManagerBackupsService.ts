/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerBackupListResponse } from '../models/ManagerBackupListResponse';
import type { ManagerBackupRunStartResponse } from '../models/ManagerBackupRunStartResponse';
import type { ManagerBackupRunStatusResponse } from '../models/ManagerBackupRunStatusResponse';
import type { ManagerRestoreJobStartResponse } from '../models/ManagerRestoreJobStartResponse';
import type { ManagerRestoreJobStatusResponse } from '../models/ManagerRestoreJobStatusResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerBackupsService {
    /**
     * List Manager Backups
     * @returns ManagerBackupListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerBackups(): CancelablePromise<ManagerBackupListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/backups',
        });
    }
    /**
     * Start Manager Backup Run
     * @returns ManagerBackupRunStartResponse Successful Response
     * @throws ApiError
     */
    public static startManagerBackupRun(): CancelablePromise<ManagerBackupRunStartResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/backups/run',
        });
    }
    /**
     * Get Manager Backup Run Status
     * @param jobId
     * @returns ManagerBackupRunStatusResponse Successful Response
     * @throws ApiError
     */
    public static getManagerBackupRunStatus(
        jobId: string,
    ): CancelablePromise<ManagerBackupRunStatusResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/backups/run/{job_id}',
            path: {
                'job_id': jobId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Start Manager Backup Restore
     * @param fileId
     * @returns ManagerRestoreJobStartResponse Successful Response
     * @throws ApiError
     */
    public static startManagerBackupRestore(
        fileId: string,
    ): CancelablePromise<ManagerRestoreJobStartResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/backups/restore/{file_id}',
            path: {
                'file_id': fileId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Manager Backup Restore Status
     * @param jobId
     * @returns ManagerRestoreJobStatusResponse Successful Response
     * @throws ApiError
     */
    public static getManagerBackupRestoreStatus(
        jobId: string,
    ): CancelablePromise<ManagerRestoreJobStatusResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/backups/restore/{job_id}',
            path: {
                'job_id': jobId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
