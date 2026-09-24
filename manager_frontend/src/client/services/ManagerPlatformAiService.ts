/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ConnectionStatus } from '../models/ConnectionStatus';
import type { ConnectionUpdate } from '../models/ConnectionUpdate';
import type { InferenceTest } from '../models/InferenceTest';
import type { ModelList } from '../models/ModelList';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerPlatformAiService {
    /**
     * Get Platform Ai
     * @returns ConnectionStatus Successful Response
     * @throws ApiError
     */
    public static getPlatformAiConnection(): CancelablePromise<ConnectionStatus> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/platform-ai',
        });
    }
    /**
     * Put Platform Ai
     * @param requestBody
     * @returns ConnectionStatus Successful Response
     * @throws ApiError
     */
    public static putPlatformAiConnection(
        requestBody: ConnectionUpdate,
    ): CancelablePromise<ConnectionStatus> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/platform-ai',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Platform Ai
     * @returns ConnectionStatus Successful Response
     * @throws ApiError
     */
    public static deletePlatformAiConnection(): CancelablePromise<ConnectionStatus> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/platform-ai',
        });
    }
    /**
     * Get Platform Ai Models
     * @returns ModelList Successful Response
     * @throws ApiError
     */
    public static getPlatformAiModels(): CancelablePromise<ModelList> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/platform-ai/models',
        });
    }
    /**
     * Test Platform Ai
     * @returns InferenceTest Successful Response
     * @throws ApiError
     */
    public static testPlatformAiInference(): CancelablePromise<InferenceTest> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/platform-ai/test',
        });
    }
}
