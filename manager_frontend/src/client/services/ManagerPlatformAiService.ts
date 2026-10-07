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
     * Read configured/enabled/selected_model state of the shared ZAPRO.SU platform connection.
     * Requires a system-tenant owner/admin. Never returns the stored key and does not contact the
     * provider; configured means a database connection record exists, not that live inference has
     * succeeded.
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
     * Save the shared ZAPRO.SU key, enabled flag and selected model; requires a system-tenant
     * owner/admin. A nonblank key replaces encrypted credentials; blank/omitted key preserves
     * them, so a first save needs a key. Omitted enabled/model preserve existing values; an empty
     * model clears it. Enabling requires a model. Returns public state without secrets;
     * invalid/not-configured values return 422 and credential-store errors 503 with detail.code.
     * Saving does not test provider access and has no replay receipt.
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
     * Delete the shared ZAPRO.SU credential record and return configured=false, enabled=false,
     * selected_model=null. Requires a system-tenant owner/admin. Repeating after deletion returns
     * the same public state. This removes local credentials; it does not revoke the provider-side
     * key or issue a provider call.
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
     * Fetch the model list from ZAPRO.SU using the stored shared key; requires a system-tenant
     * owner/admin. The connection need not be enabled. This is a live provider request, not a
     * static model catalog. Missing/invalid configuration returns 422, credential-store errors 503
     * and provider failures 502 with detail.code.
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
     * Send a small live inference request to the selected ZAPRO.SU model using shared platform
     * credentials, even if the connection is disabled. Requires a system-tenant owner/admin.
     * Returns ok, model and reported token usage; the call may consume provider quota and repeats
     * perform inference again. Missing model/configuration returns 422, unreadable credentials 503
     * and provider failure 502 with detail.code. Does not enable the connection.
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
     * Read effective shared DeepSeek configuration without returning its key; requires a
     * system-tenant owner/admin. source=settings means a database record controls the connection,
     * including an explicitly deleted/disabled record. Environment fallback applies only while no
     * settings record exists. environment_key_available reports availability, not that the
     * environment key is currently used; no provider call is made.
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
     * Save shared DeepSeek credentials/enabled state for a system-tenant owner/admin. A nonblank
     * key replaces encrypted credentials; otherwise an existing key is retained. On the first
     * save, an available environment key is copied into settings, after which there is no
     * automatic environment fallback. Enabling without a key returns 422; credential-store errors
     * return 503 with detail.code. Returns public state without testing provider access or a
     * replay receipt.
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
     * Clear stored DeepSeek credentials and explicitly disable the shared connection; requires a
     * system-tenant owner/admin. Keeps a settings record so an environment key does not silently
     * reactivate the connection. Repeating leaves it disabled. Returns public state without
     * revoking the provider-side key or calling the provider.
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
     * Copy the available environment DeepSeek key into encrypted settings and enable the shared
     * connection; requires a system-tenant owner/admin. Existing configured settings return 409
     * already_configured, including a repeat after successful import; missing environment key
     * returns 422 and credential-store errors 503. Returns public state, never the key, and does
     * not verify provider inference.
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
     * Send a small live JSON inference request with the effective shared DeepSeek key, even when
     * saved settings are disabled. Requires a system-tenant owner/admin; an explicit deletion
     * still suppresses environment fallback. Returns ok without enabling or updating settings.
     * Repeats consume another provider request. Missing configuration returns 422, unreadable
     * credentials 503 and provider/invalid-response failures 502 with detail.code.
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
     * Read Jev configuration status, fixed model, daily limits and today’s UTC usage. The
     * encrypted credential itself is never returned. This does not test the credential or make
     * a provider request.
     *
     * Access and scope: system-tenant owner/admin access is required; these settings control
     * the platform Jev connection. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Save submitted Jev connection settings and encrypt a nonblank key; omitted/blank keys
     * preserve the existing credential. Enabling requires a configured credential;
     * daily_budget_usd is greater than zero and at most 5. Invalid configuration returns 422
     * and unavailable/unreadable credential storage 503 with safe error codes. Saving does not
     * perform inference or fall back to an environment credential.
     *
     * Access and scope: system-tenant owner/admin access is required; these settings control
     * the platform Jev connection. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Clear the stored Jev credential/fingerprint and disable the connection, returning its
     * public status. Budget settings and usage history remain; repeating is safe. This removes
     * local configuration without revoking the provider credential externally.
     *
     * Access and scope: system-tenant owner/admin access is required; these settings control
     * the platform Jev connection. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Run a fixed Jev test inference using the stored credential, even if regular inference is
     * disabled. The request reserves usage/budget before calling the provider, so repeats
     * consume budget again. Missing credential or exhausted budget returns 422,
     * credential-store failures 503 and provider failures 502. The test does not classify or
     * modify a business record.
     *
     * Access and scope: system-tenant owner/admin access is required; these settings control
     * the platform Jev connection. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Read saved Jev shadow-comparison counts, costs, timing and sample records, optionally
     * filtered by email/belzakupki source and disagreements. limit is 1–100. This does not
     * rescore inputs, change primary classifications or trigger provider calls.
     *
     * Access and scope: system-tenant owner/admin access is required; report rows are
     * restricted to the authenticated system tenant. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
