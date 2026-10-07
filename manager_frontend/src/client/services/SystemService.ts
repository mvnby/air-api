/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { WebRebuildCompletePayload } from '../models/WebRebuildCompletePayload';
import type { WebRebuildStatusResponse } from '../models/WebRebuildStatusResponse';
import type { WebRebuildTriggerResponse } from '../models/WebRebuildTriggerResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class SystemService {
    /**
     * Get Rebuild Web Status
     * Read global catalog revision and storefront synchronization acknowledgement state for an
     * authenticated Manager. This is platform-wide catalog publication state, not a per-tenant job
     * or a deployment health check. Reading does not dispatch a workflow; the recorded
     * acknowledgement alone does not verify current storefront availability.
     * @returns WebRebuildStatusResponse Successful Response
     * @throws ApiError
     */
    public static getRebuildWebStatusApiSystemRebuildWebStatusGet(): CancelablePromise<WebRebuildStatusResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/system/rebuild-web/status',
        });
    }
    /**
     * Trigger Rebuild Web
     * Dispatch the standalone storefront's catalog synchronization workflow for the current global
     * revision, then record that revision as requested. Requires Manager access. A missing GitHub
     * integration token returns 503; dispatch failure returns 500. A successful response
     * acknowledges dispatch, not completed synchronization; read /api/system/rebuild-web/status
     * afterward. No Idempotency-Key receipt prevents repeated workflow dispatches.
     * @returns WebRebuildTriggerResponse Successful Response
     * @throws ApiError
     */
    public static triggerRebuildWebApiSystemRebuildWebPost(): CancelablePromise<WebRebuildTriggerResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/system/rebuild-web',
        });
    }
    /**
     * Complete Rebuild Web
     * Record the standalone storefront's catalog synchronization callback using the shared
     * X-Web-Rebuild-Token header, not a Manager JWT or an HMAC signature. Missing server token
     * configuration returns 503; invalid token returns 403. Revision zero resolves to the current
     * revision. Success stores the supplied published revision/timestamp and clears the error;
     * failure stores requested revision/error. This writes global state, has no replay receipt or
     * monotonic-revision guard, and repeated or out-of-order callbacks can replace recorded state.
     * It does not itself verify the storefront.
     * @param requestBody
     * @param xWebRebuildToken
     * @returns WebRebuildStatusResponse Successful Response
     * @throws ApiError
     */
    public static completeRebuildWebApiSystemRebuildWebCompletePost(
        requestBody: WebRebuildCompletePayload,
        xWebRebuildToken?: (string | null),
    ): CancelablePromise<WebRebuildStatusResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/system/rebuild-web/complete',
            headers: {
                'X-Web-Rebuild-Token': xWebRebuildToken,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
