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
     * Return whether the static Astro storefront is behind catalog data.
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
     * Trigger a turbo-rebuild of the frontend Astro site.
     * Accessible only by authenticated managers/admins.
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
     * Callback for GitHub Actions after the static storefront deploy completes.
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
