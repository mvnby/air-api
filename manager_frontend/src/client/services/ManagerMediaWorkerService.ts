/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_complete_media_worker_job } from '../models/Body_complete_media_worker_job';
import type { ManagerMediaProcessingJobResponse } from '../models/ManagerMediaProcessingJobResponse';
import type { MediaWorkerClaimPayload } from '../models/MediaWorkerClaimPayload';
import type { MediaWorkerClaimResponse } from '../models/MediaWorkerClaimResponse';
import type { MediaWorkerFailPayload } from '../models/MediaWorkerFailPayload';
import type { MediaWorkerRenewPayload } from '../models/MediaWorkerRenewPayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerMediaWorkerService {
    /**
     * Claim Media Worker Job
     * @param requestBody
     * @param authorization
     * @param xMediaWorkerToken
     * @returns MediaWorkerClaimResponse Successful Response
     * @throws ApiError
     */
    public static claimMediaWorkerJob(
        requestBody: MediaWorkerClaimPayload,
        authorization?: (string | null),
        xMediaWorkerToken?: (string | null),
    ): CancelablePromise<MediaWorkerClaimResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/media/worker/jobs/claim',
            headers: {
                'authorization': authorization,
                'x-media-worker-token': xMediaWorkerToken,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Renew Media Worker Job
     * @param jobId
     * @param requestBody
     * @param authorization
     * @param xMediaWorkerToken
     * @returns ManagerMediaProcessingJobResponse Successful Response
     * @throws ApiError
     */
    public static renewMediaWorkerJob(
        jobId: string,
        requestBody: MediaWorkerRenewPayload,
        authorization?: (string | null),
        xMediaWorkerToken?: (string | null),
    ): CancelablePromise<ManagerMediaProcessingJobResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/media/worker/jobs/{job_id}/renew',
            path: {
                'job_id': jobId,
            },
            headers: {
                'authorization': authorization,
                'x-media-worker-token': xMediaWorkerToken,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Complete Media Worker Job
     * @param jobId
     * @param formData
     * @param authorization
     * @param xMediaWorkerToken
     * @returns ManagerMediaProcessingJobResponse Successful Response
     * @throws ApiError
     */
    public static completeMediaWorkerJob(
        jobId: string,
        formData: Body_complete_media_worker_job,
        authorization?: (string | null),
        xMediaWorkerToken?: (string | null),
    ): CancelablePromise<ManagerMediaProcessingJobResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/media/worker/jobs/{job_id}/complete',
            path: {
                'job_id': jobId,
            },
            headers: {
                'authorization': authorization,
                'x-media-worker-token': xMediaWorkerToken,
            },
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Fail Media Worker Job
     * @param jobId
     * @param requestBody
     * @param authorization
     * @param xMediaWorkerToken
     * @returns ManagerMediaProcessingJobResponse Successful Response
     * @throws ApiError
     */
    public static failMediaWorkerJob(
        jobId: string,
        requestBody: MediaWorkerFailPayload,
        authorization?: (string | null),
        xMediaWorkerToken?: (string | null),
    ): CancelablePromise<ManagerMediaProcessingJobResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/media/worker/jobs/{job_id}/fail',
            path: {
                'job_id': jobId,
            },
            headers: {
                'authorization': authorization,
                'x-media-worker-token': xMediaWorkerToken,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
