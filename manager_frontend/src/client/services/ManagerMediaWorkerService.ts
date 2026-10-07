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
     * Atomically claim the next queued job or reclaim an expired running attempt, ordered by
     * priority then creation time and filtered by worker capabilities. Empty capabilities
     * means no capability filter. Returns job=null when none can be claimed; a claim
     * increments attempts and rotates lease_token. Keep the returned worker_id/token pair for
     * renew/complete/fail; a later claim is a new attempt.
     *
     * Access and scope: the configured MEDIA_WORKER_TOKEN is required via Authorization:
     * Bearer or X-Media-Worker-Token (the latter takes precedence). Missing/invalid token
     * returns 401; an unconfigured server token returns 503. Manager JWT/cookies do not
     * authorize this endpoint.
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
     * Extend an unexpired running attempt owned by the supplied worker_id and lease_token.
     * Unknown job returns 404; stale token, changed owner/status or expired lease returns 409.
     * The expiry is set from renewal time, so repetition may extend it again. Renew before
     * expiration; expired leases can be reclaimed by another worker.
     *
     * Access and scope: the configured MEDIA_WORKER_TOKEN is required via Authorization:
     * Bearer or X-Media-Worker-Token (the latter takes precedence). Missing/invalid token
     * returns 401; an unconfigured server token returns 503. Manager JWT/cookies do not
     * authorize this endpoint.
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
     * Complete an unexpired owned attempt from multipart processed-image bytes and create a
     * result child library asset. worker_id and lease_token must match the running attempt;
     * missing job/source returns 404, invalid/stale/expired lease or invalid result returns
     * 409, and more than 50 MB returns 413. Success clears the lease and marks the job
     * successful; a repeat is rejected with 409, not replayed.
     *
     * Access and scope: the configured MEDIA_WORKER_TOKEN is required via Authorization:
     * Bearer or X-Media-Worker-Token (the latter takes precedence). Missing/invalid token
     * returns 401; an unconfigured server token returns 503. Manager JWT/cookies do not
     * authorize this endpoint. See [media
     * publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
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
     * Mark an unexpired running attempt failed with the supplied error, truncated to 2000
     * characters, and clear its lease. Unknown job returns 404; stale token, wrong owner or
     * expired/finished attempt returns 409. Failed jobs are not automatically claimable;
     * repetition after success of this command returns 409.
     *
     * Access and scope: the configured MEDIA_WORKER_TOKEN is required via Authorization:
     * Bearer or X-Media-Worker-Token (the latter takes precedence). Missing/invalid token
     * returns 401; an unconfigured server token returns 503. Manager JWT/cookies do not
     * authorize this endpoint.
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
