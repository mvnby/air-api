/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ConnectionStatus } from '../models/ConnectionStatus';
import type { ConnectionUpdate } from '../models/ConnectionUpdate';
import type { DeepseekConnectionStatus } from '../models/DeepseekConnectionStatus';
import type { DeepseekConnectionTest } from '../models/DeepseekConnectionTest';
import type { DeepseekConnectionUpdate } from '../models/DeepseekConnectionUpdate';
import type { InferenceTest } from '../models/InferenceTest';
import type { JevShadowReport } from '../models/JevShadowReport';
import type { JevStatus } from '../models/JevStatus';
import type { JevTest } from '../models/JevTest';
import type { JevUpdate } from '../models/JevUpdate';
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
    /**
     * Get Deepseek Connection
     * @returns DeepseekConnectionStatus Successful Response
     * @throws ApiError
     */
    public static getDeepseekConnection(): CancelablePromise<DeepseekConnectionStatus> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/platform-ai/deepseek',
        });
    }
    /**
     * Put Deepseek Connection
     * @param requestBody
     * @returns DeepseekConnectionStatus Successful Response
     * @throws ApiError
     */
    public static putDeepseekConnection(
        requestBody: DeepseekConnectionUpdate,
    ): CancelablePromise<DeepseekConnectionStatus> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/platform-ai/deepseek',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Deepseek Connection
     * @returns DeepseekConnectionStatus Successful Response
     * @throws ApiError
     */
    public static deleteDeepseekConnection(): CancelablePromise<DeepseekConnectionStatus> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/platform-ai/deepseek',
        });
    }
    /**
     * Import Deepseek Environment Key
     * @returns DeepseekConnectionStatus Successful Response
     * @throws ApiError
     */
    public static importDeepseekEnvironmentKey(): CancelablePromise<DeepseekConnectionStatus> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/platform-ai/deepseek/import-environment',
        });
    }
    /**
     * Test Deepseek Connection
     * @returns DeepseekConnectionTest Successful Response
     * @throws ApiError
     */
    public static testDeepseekConnection(): CancelablePromise<DeepseekConnectionTest> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/platform-ai/deepseek/test',
        });
    }
    /**
     * Get Jev Connection
     * @returns JevStatus Successful Response
     * @throws ApiError
     */
    public static getJevConnection(): CancelablePromise<JevStatus> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/platform-ai/jev',
        });
    }
    /**
     * Put Jev Connection
     * @param requestBody
     * @returns JevStatus Successful Response
     * @throws ApiError
     */
    public static putJevConnection(
        requestBody: JevUpdate,
    ): CancelablePromise<JevStatus> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/platform-ai/jev',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Jev Connection
     * @returns JevStatus Successful Response
     * @throws ApiError
     */
    public static deleteJevConnection(): CancelablePromise<JevStatus> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/platform-ai/jev',
        });
    }
    /**
     * Test Jev Connection
     * @returns JevTest Successful Response
     * @throws ApiError
     */
    public static testJevConnection(): CancelablePromise<JevTest> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/platform-ai/jev/test',
        });
    }
    /**
     * Get Jev Shadow Report
     * @param source
     * @param disagreementsOnly
     * @param limit
     * @returns JevShadowReport Successful Response
     * @throws ApiError
     */
    public static getJevShadowReport(
        source?: ('email' | 'belzakupki' | null),
        disagreementsOnly: boolean = false,
        limit: number = 20,
    ): CancelablePromise<JevShadowReport> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/platform-ai/jev/shadow',
            query: {
                'source': source,
                'disagreements_only': disagreementsOnly,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
