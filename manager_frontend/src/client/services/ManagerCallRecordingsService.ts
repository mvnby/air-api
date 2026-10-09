/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CallAdoptionResponse } from '../models/CallAdoptionResponse';
import type { CallAdoptPayload } from '../models/CallAdoptPayload';
import type { CallDriveFileListResponse } from '../models/CallDriveFileListResponse';
import type { CallDriveStatus } from '../models/CallDriveStatus';
import type { CallFolderPayload } from '../models/CallFolderPayload';
import type { CallPollPayload } from '../models/CallPollPayload';
import type { CallPollResponse } from '../models/CallPollResponse';
import type { CallRecordingListResponse } from '../models/CallRecordingListResponse';
import type { CallRecordingMetadataPayload } from '../models/CallRecordingMetadataPayload';
import type { CallRecordingResponse } from '../models/CallRecordingResponse';
import type { CallRetryPayload } from '../models/CallRetryPayload';
import type { DocumentDriveAuthorizationUrlResponse } from '../models/DocumentDriveAuthorizationUrlResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerCallRecordingsService {
    /**
     * Connection Status
     * Read personal call-Drive connection readiness and fixed processing limits. Requires
     * live Manager membership and explicit private-pilot access; scope is the current staff user plus tenant/storefront,
     * including owners (no access to another user's calls). Returns no credentials. Does
     * not contact Drive, poll recordings or charge AI. Default pipeline is disabled.
     * [Call contract](https://github.com/mvnby/air-api/blob/main/docs/call-recordings.md).
     * @returns CallDriveStatus Successful Response
     * @throws ApiError
     */
    public static getManagerCallDriveStatus(): CancelablePromise<CallDriveStatus> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/call-recordings/connection',
        });
    }
    /**
     * Disconnect
     * Remove this user's local call-Drive credential and stop automatic polling. Live
     * writable Manager membership required. Retains source links, transcripts, proposals and
     * accepted actions; does not delete Google files or revoke other integrations. Repeating
     * the disconnect is safe. Queued jobs fail closed until explicit reconnection/retry.
     * @returns CallDriveStatus Successful Response
     * @throws ApiError
     */
    public static disconnectManagerCallDrive(): CancelablePromise<CallDriveStatus> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/call-recordings/connection',
        });
    }
    /**
     * Authorization Url
     * Start a separate personal Google Drive readonly OAuth grant for the live staff
     * actor/current tenant/storefront. State is one-use, expires after 10 minutes, and
     * callback rechecks live role, membership and auth version. Existing document drive.file
     * grants cannot read Samsung uploads. No Shared Drive is required. Does not choose a
     * folder or enable polling; missing server OAuth configuration returns 503/502.
     * [Call contract](https://github.com/mvnby/air-api/blob/main/docs/call-recordings.md).
     * @returns DocumentDriveAuthorizationUrlResponse Successful Response
     * @throws ApiError
     */
    public static getManagerCallDriveAuthorizationUrl(): CancelablePromise<DocumentDriveAuthorizationUrlResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/call-recordings/authorization-url',
        });
    }
    /**
     * Configure Folder
     * Select an existing accessible folder for this staff user's separate readonly
     * Drive grant. Live Manager access and writable tenant required. Personal Drive is
     * supported. Verifies folder metadata, never creates a folder or reads audio. Explicit
     * auto_poll_enabled opt-in also requires server CALL_RECORDINGS_ENABLED before jobs run;
     * default false. Folder changes reset scan cursor and retain existing review material.
     * Same payload is safe to repeat. Invalid/unavailable folder returns 422/409/502.
     * @param requestBody
     * @returns CallDriveStatus Successful Response
     * @throws ApiError
     */
    public static configureManagerCallDriveFolder(
        requestBody: CallFolderPayload,
    ): CancelablePromise<CallDriveStatus> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/call-recordings/connection/folder',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Drive Files
     * Read audio metadata only from the current private pilot's selected folder.
     * Inclusive Minsk call dates and contact/phone are parsed from Samsung filenames;
     * unknown dates never use Drive sync/modified time. Returns at most 100 matches
     * and a continuation token, scanning at most five metadata pages per request.
     * Never downloads audio, advances the automatic cursor, queues AI or adopts work.
     * Current personal live access is rechecked after provider I/O. OAuth credentials
     * may be refreshed; no pipeline opt-in or transcription configuration is required.
     * @param dateFrom
     * @param dateTo
     * @param query
     * @param pageToken
     * @returns CallDriveFileListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerCallDriveFiles(
        dateFrom?: (string | null),
        dateTo?: (string | null),
        query: string = '',
        pageToken?: (string | null),
    ): CancelablePromise<CallDriveFileListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/call-recordings/drive/files',
            query: {
                'date_from': dateFrom,
                'date_to': dateTo,
                'query': query,
                'page_token': pageToken,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Poll
     * Explicitly observe at most five files from the chosen personal folder (or one
     * file_id for a pilot), using metadata only. Live writable Manager access, separate OAuth
     * grant, selected folder and server-enabled pipeline required. Two observations at least
     * 60 seconds apart and stable version/checksum/size enqueue a durable job; this response
     * is not successful transcription. New versions keep old material. At most 20 new
     * recordings per owner per rolling day. Repeated observations do not duplicate jobs.
     * Disabled 503, missing connection/folder or moved/unfinished chosen file 409, rejected
     * format/size 422 and Drive failures 502. Job acceptance remains a separate command.
     * @param requestBody
     * @returns CallPollResponse Successful Response
     * @throws ApiError
     */
    public static pollManagerCallRecordings(
        requestBody: CallPollPayload,
    ): CancelablePromise<CallPollResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/call-recordings/poll',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Recordings
     * List private call versions for the live Manager actor/current tenant/storefront,
     * newest first; limit <=100 and offset pagination, including total. Other staff users,
     * companies and storefronts are invisible. Returns stage, source link, error code and
     * paid-stage attempt counts without transcript/audio bytes. Reading never starts work.
     * @param limit
     * @param offset
     * @returns CallRecordingListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerCallRecordings(
        limit: number = 50,
        offset?: number,
    ): CancelablePromise<CallRecordingListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/call-recordings',
            query: {
                'limit': limit,
                'offset': offset,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Recording
     * Read this staff user's scoped source version, transcript, structured review result
     * and separately editable proposals with accepted-resource links. Requires live Manager
     * role/membership; missing or inaccessible ID returns 404. Source Google link retains
     * Google's own access policy. Proposed dates/conditions never confirm visits or facts;
     * reading does not accept proposals, send messages or call AI.
     * @param recordingId
     * @returns CallRecordingResponse Successful Response
     * @throws ApiError
     */
    public static getManagerCallRecording(
        recordingId: number,
    ): CancelablePromise<CallRecordingResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/call-recordings/{recording_id}',
            path: {
                'recording_id': recordingId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Metadata
     * Explicitly correct/clear source call time and phone for this user's recording.
     * Requires live writable Manager access and expected_version; busy/stale version 409,
     * missing 404, invalid phone/date 422. Sets time_source=manual (or unknown on null).
     * Existing extraction/transcript is preserved; proposal rebuilding needs explicit retry
     * and reuses successful paid checkpoints. Retrying a successful write with an old version
     * returns 409; read the current version. Never infers time from processing/sync date.
     * @param recordingId
     * @param requestBody
     * @returns CallRecordingResponse Successful Response
     * @throws ApiError
     */
    public static updateManagerCallRecordingMetadata(
        recordingId: number,
        requestBody: CallRecordingMetadataPayload,
    ): CancelablePromise<CallRecordingResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/call-recordings/{recording_id}/metadata',
            path: {
                'recording_id': recordingId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Retry
     * Explicitly resume a failed/reconnect/manual-review recording at the first unfinished
     * stage. Requires live writable scoped Manager access, server opt-in and expected_version.
     * Retains successful download/transcription/extraction checkpoints and does not recreate
     * adopted incoming/tasks. No reset of the three-attempt paid-stage cap. Busy/stale/ready
     * or exhausted stage 409; missing 404; disabled 503. Read current state after ambiguous
     * response rather than repeating with a stale version. Reconnect OAuth before access retry.
     * @param recordingId
     * @param requestBody
     * @returns CallRecordingResponse Successful Response
     * @throws ApiError
     */
    public static retryManagerCallRecording(
        recordingId: number,
        requestBody: CallRetryPayload,
    ): CancelablePromise<CallRecordingResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/call-recordings/{recording_id}/retry',
            path: {
                'recording_id': recordingId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Adopt
     * Explicitly adopt ONE edited proposal as a persistent Incoming or personal task,
     * using the shared authenticated commands. Incoming clarification_requested also creates
     * its disclosed linked clarification task. Requires current live writable Manager actor,
     * original private source ownership, ready state and expected_version; foreign/missing
     * 404, stale/busy or changed accepted payload 409, invalid fields 422 and receipt storage
     * unavailable 503 with Retry-After. Durable source/action receipt and domain write/audit
     * commit atomically. Same adoption replays even beyond the ordinary receipt horizon;
     * changed Drive versions cannot reapply accepted actions. Original call time and source
     * link are retained. Does not create an order, confirm a visit or send to a customer.
     * @param recordingId
     * @param proposalId
     * @param requestBody
     * @returns CallAdoptionResponse Successful Response
     * @throws ApiError
     */
    public static adoptManagerCallProposal(
        recordingId: number,
        proposalId: number,
        requestBody: CallAdoptPayload,
    ): CancelablePromise<CallAdoptionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/call-recordings/{recording_id}/proposals/{proposal_id}/adopt',
            path: {
                'recording_id': recordingId,
                'proposal_id': proposalId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
