/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DocumentDriveAuthorizationUrlResponse } from '../models/DocumentDriveAuthorizationUrlResponse';
import type { DocumentDriveStatusResponse } from '../models/DocumentDriveStatusResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerDocumentDriveService {
    /**
     * Get Manager Document Drive Status
     * Read the optional Google Drive document-editor connection status for the current
     * tenant/storefront. Manager access is required. Returns connection readiness/labels
     * without credentials; this does not check or synchronize an individual editing session.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @returns DocumentDriveStatusResponse Successful Response
     * @throws ApiError
     */
    public static getManagerDocumentDriveStatus(): CancelablePromise<DocumentDriveStatusResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/document-drive/status',
        });
    }
    /**
     * Get Manager Document Drive Authorization Url
     * Start tenant/storefront-bound Google Drive OAuth consent and return its authorization
     * URL. Requires owner/admin access; binds pending state to the live actor and browser
     * session. Misconfigured redirect returns 503; provider policy errors keep their status.
     * Obtaining the URL does not complete the connection and a new request replaces pending
     * consent state.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @returns DocumentDriveAuthorizationUrlResponse Successful Response
     * @throws ApiError
     */
    public static getManagerDocumentDriveAuthorizationUrl(): CancelablePromise<DocumentDriveAuthorizationUrlResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/document-drive/authorization-url',
        });
    }
}
