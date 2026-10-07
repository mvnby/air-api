/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerGoogleAuthStatusResponse } from '../models/ManagerGoogleAuthStatusResponse';
import type { ManagerGoogleAuthUrlResponse } from '../models/ManagerGoogleAuthUrlResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerGoogleAuthService {
    /**
     * Get Manager Google Auth Status
     * Read the shared platform Google credential status for a system-tenant owner/admin. Reports
     * the Google service's token status without returning OAuth tokens; provider/service failure
     * returns 502. This is the shared Drive/document integration, distinct from tenant/storefront
     * analytics connections.
     * @returns ManagerGoogleAuthStatusResponse Successful Response
     * @throws ApiError
     */
    public static getManagerGoogleAuthStatus(): CancelablePromise<ManagerGoogleAuthStatusResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/google-auth/status',
        });
    }
    /**
     * Get Manager Google Auth Url
     * Begin browser authorization for the shared platform Google integration; requires a
     * system-tenant owner/admin. Returns a consent URL and replaces the pending state in the
     * browser session, bound to the actor and redirect URI for ten minutes. Continue in the same
     * cookie session; the callback consumes state once before exchanging the code. This GET
     * changes session state but does not yet save Google credentials. Redirect configuration
     * failure returns 503; service failure returns 502. Tenant analytics has separate
     * authorization endpoints.
     * @returns ManagerGoogleAuthUrlResponse Successful Response
     * @throws ApiError
     */
    public static getManagerGoogleAuthUrl(): CancelablePromise<ManagerGoogleAuthUrlResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/google-auth/url',
        });
    }
}
