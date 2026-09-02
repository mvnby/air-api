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
