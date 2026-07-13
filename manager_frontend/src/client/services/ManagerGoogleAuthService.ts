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
