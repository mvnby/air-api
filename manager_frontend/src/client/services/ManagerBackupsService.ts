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
     * List up to 100 configured Google Drive backup entries for a system-tenant owner/admin. These
     * are platform database/media backups, not tenant exports; listing performs no restore.
     * Unconfigured storage returns 503 and credential/provider listing failures return 502 with
     * detail.error_code=backup_list_unavailable in the Manager error envelope.
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
     * Start a manual platform backup in the API process and return 202 with job_id/status/stage.
     * Requires a system-tenant owner/admin and production environment (otherwise 400). A known
     * active backup or restore returns 409; startup failure returns 500. Poll
     * /api/manager/backups/run/{job_id}; 202 is acceptance, not backup success. Job records and
     * exclusion locks are process-local and do not survive restart or provide an HA-wide lock. No
     * replay key is supported.
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
     * Read a manual backup job from this API process's in-memory registry; requires a
     * system-tenant owner/admin. Returns status/stage/timestamps and error, with success/failed
     * terminal outcomes. Unknown jobs return 404, including after a process restart or on another
     * worker/node. This endpoint neither starts nor retries a backup.
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
     * Start restoration of a configured platform database or media backup and return 202 with a
     * job ID. Requires a system-tenant owner/admin and BACKUP_RESTORE_ENABLED; normal operation
     * returns 503 because restore is disabled. This can replace shared production data and belongs
     * to the supervised [production-data
     * procedure](https://github.com/mvnby/air-api/blob/main/docs/production-data-operations.md).
     * Known active jobs return 409, an unlisted file 404 and unsupported kind 400. The job first
     * creates a safety copy; completion/failure must be polled. State and exclusion locks are
     * process-local, without an HA-wide lock or replay receipt.
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
     * Read a restore job from this API process's in-memory registry; requires a system-tenant
     * owner/admin. Includes stage, terminal success/failed, error and safety-copy path when
     * available. Unknown jobs return 404, including after restart or when polling a different
     * worker/node. Reading status does not enable, start or repeat restoration.
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
