/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AnalyticsAuthorizationUrlResponse } from '../models/AnalyticsAuthorizationUrlResponse';
import type { AnalyticsConnectionItem } from '../models/AnalyticsConnectionItem';
import type { AnalyticsConnectionListResponse } from '../models/AnalyticsConnectionListResponse';
import type { GoogleAdsAuthorizationPayload } from '../models/GoogleAdsAuthorizationPayload';
import type { GoogleAnalyticsAuthorizationPayload } from '../models/GoogleAnalyticsAuthorizationPayload';
import type { YandexDirectConnectionUpsertPayload } from '../models/YandexDirectConnectionUpsertPayload';
import type { YandexMetrikaConnectionUpsertPayload } from '../models/YandexMetrikaConnectionUpsertPayload';
import type { YandexWebmasterConnectionUpsertPayload } from '../models/YandexWebmasterConnectionUpsertPayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerAnalyticsConnectionsService {
    /**
     * List Manager Analytics Connections
     * Read analytics-provider connection states and public configuration for the current
     * tenant/storefront; requires a current-tenant owner/admin. Includes available/unconfigured
     * providers and stored verification/error state, without tokens. Reads may detect unreadable
     * stored credentials; connected status does not constitute a new live provider verification.
     * This does not use the platform Google Drive credentials.
     * @returns AnalyticsConnectionListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerAnalyticsConnections(): CancelablePromise<AnalyticsConnectionListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/analytics-connections',
        });
    }
    /**
     * Upsert Manager Yandex Metrika Connection
     * Verify the supplied Yandex Metrika counter/token with the provider, then save encrypted
     * credentials and public counter metadata for the current storefront with an audit event.
     * Requires a current-tenant owner/admin. A blank or omitted token reuses stored credentials;
     * first connection requires a token. Validation/provider failures use
     * detail.error_code/message and do not confirm a connection. Repeats re-verify and save; no
     * command replay receipt is provided.
     * @param requestBody
     * @returns AnalyticsConnectionItem Successful Response
     * @throws ApiError
     */
    public static upsertManagerYandexMetrikaConnection(
        requestBody: YandexMetrikaConnectionUpsertPayload,
    ): CancelablePromise<AnalyticsConnectionItem> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/analytics-connections/yandex-metrika',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Upsert Manager Yandex Direct Connection
     * Verify Yandex Direct access for the optional client_login, then save encrypted
     * credentials/public configuration for the current tenant/storefront and audit the change.
     * Requires a current-tenant owner/admin. A blank/omitted token reuses this storefront's stored
     * token; otherwise a token is required. Invalid/provider-denied configuration returns 422;
     * retryable or unexpected provider failure returns 502 with detail.error_code/message.
     * Repeating PUT repeats provider verification rather than replaying a receipt.
     * @param requestBody
     * @returns AnalyticsConnectionItem Successful Response
     * @throws ApiError
     */
    public static upsertManagerYandexDirectConnection(
        requestBody: YandexDirectConnectionUpsertPayload,
    ): CancelablePromise<AnalyticsConnectionItem> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/analytics-connections/yandex-direct',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Upsert Manager Yandex Webmaster Connection
     * Verify Yandex Webmaster access to the current storefront's active primary hostname, then
     * store encrypted credentials/public configuration and audit the change. Requires a
     * current-tenant owner/admin; the caller cannot supply another storefront's hostname.
     * Blank/omitted token reuses stored credentials. Missing primary domain or denied/unverified
     * access returns 422; retryable provider failure returns 502 with detail.error_code/message.
     * Repeats re-verify the connection; no command replay receipt exists.
     * @param requestBody
     * @returns AnalyticsConnectionItem Successful Response
     * @throws ApiError
     */
    public static upsertManagerYandexWebmasterConnection(
        requestBody: YandexWebmasterConnectionUpsertPayload,
    ): CancelablePromise<AnalyticsConnectionItem> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/analytics-connections/yandex-webmaster',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Start Manager Google Analytics Authorization
     * Begin Google Analytics authorization for property_id in the current tenant/storefront;
     * requires a current-tenant owner/admin. Returns a consent URL and replaces pending analytics
     * OAuth state in the browser session, bound to actor/scope and provider configuration.
     * Complete the callback in that cookie session to save credentials; this request does not
     * connect the provider yet. Configuration/unavailable OAuth returns 503 with
     * detail.error_code/message. Starting another analytics flow supersedes the pending one.
     * @param requestBody
     * @returns AnalyticsAuthorizationUrlResponse Successful Response
     * @throws ApiError
     */
    public static startManagerGoogleAnalyticsAuthorization(
        requestBody: GoogleAnalyticsAuthorizationPayload,
    ): CancelablePromise<AnalyticsAuthorizationUrlResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/analytics-connections/google-analytics/authorization-url',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Start Manager Google Search Console Authorization
     * Begin Google Search Console authorization for the current storefront's active primary
     * hostname; requires a current-tenant owner/admin. Missing primary domain returns 422 with
     * storefront_domain_unavailable. Returns a consent URL and replaces browser-session analytics
     * state; credentials are saved only after the callback and provider verification in that
     * session. OAuth configuration/unavailability returns 503. The hostname is server-resolved,
     * and a later analytics authorization replaces this pending flow.
     * @returns AnalyticsAuthorizationUrlResponse Successful Response
     * @throws ApiError
     */
    public static startManagerGoogleSearchConsoleAuthorization(): CancelablePromise<AnalyticsAuthorizationUrlResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/analytics-connections/google-search-console/authorization-url',
        });
    }
    /**
     * Start Manager Google Ads Authorization
     * Begin Google Ads authorization for customer_id and optional login_customer_id in the current
     * storefront; requires a current-tenant owner/admin. A configured platform developer token is
     * required or returns 503 with google_ads_system_not_configured. Returns a consent URL and
     * replaces actor/scope-bound analytics state in the browser session. Complete the callback in
     * that cookie session to verify and save the connection; this request alone does not save
     * credentials. Other OAuth configuration/unavailability failures also return 503.
     * @param requestBody
     * @returns AnalyticsAuthorizationUrlResponse Successful Response
     * @throws ApiError
     */
    public static startManagerGoogleAdsAuthorization(
        requestBody: GoogleAdsAuthorizationPayload,
    ): CancelablePromise<AnalyticsAuthorizationUrlResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/analytics-connections/google-ads/authorization-url',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
