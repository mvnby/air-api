/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerBackupListResponse } from '../models/ManagerBackupListResponse';
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
