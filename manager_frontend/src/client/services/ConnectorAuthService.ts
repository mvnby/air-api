/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ConnectorGrantListResponse } from '../models/ConnectorGrantListResponse';
import type { ConnectorTokenResponse } from '../models/ConnectorTokenResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ConnectorAuthService {
    /**
     * Authorization Metadata
     * Publish OAuth authorization-server discovery for the configured issuer, supported
     * grants/scopes and PKCE S256. No Manager session is required; this does not dynamically
     * register clients.
     *
     * See [connector access and
     * scopes](https://github.com/mvnby/air-api/blob/main/docs/chatgpt-connector.md#адрес-и-доступ).
     * MCP transport and tools/list are outside this HTTP schema.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static connectorOauthMetadata(): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/.well-known/oauth-authorization-server',
        });
    }
    /**
     * Protected Resource Metadata
     * Publish OAuth protected-resource discovery for the exact MCP resource. Available at both
     * well-known paths without a Manager session. OAuth metadata is not the MCP tools catalog.
     *
     * See [connector access and
     * scopes](https://github.com/mvnby/air-api/blob/main/docs/chatgpt-connector.md#адрес-и-доступ).
     * MCP transport and tools/list are outside this HTTP schema.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static connectorOauthResourcePathMetadata(): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/.well-known/oauth-protected-resource/api/connector/mcp',
        });
    }
    /**
     * Protected Resource Metadata
     * Publish OAuth protected-resource discovery for the exact MCP resource. Available at both
     * well-known paths without a Manager session. OAuth metadata is not the MCP tools catalog.
     *
     * See [connector access and
     * scopes](https://github.com/mvnby/air-api/blob/main/docs/chatgpt-connector.md#адрес-и-доступ).
     * MCP transport and tools/list are outside this HTTP schema.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static connectorOauthResourceMetadata(): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/.well-known/oauth-protected-resource',
        });
    }
    /**
     * Authorize
     * Start a one-time OAuth consent bound to the current authenticated Manager session and
     * render an HTML consent page. Requires the registered client/callback, exact resource,
     * scopes and PKCE S256; duplicate query parameters are rejected. Missing login returns an
     * HTML 401; OAuth errors use error/error_description and no-store headers.
     *
     * See [connector access and
     * scopes](https://github.com/mvnby/air-api/blob/main/docs/chatgpt-connector.md#адрес-и-доступ).
     * MCP transport and tools/list are outside this HTTP schema.
     * @returns string Successful Response
     * @throws ApiError
     */
    public static connectorOauthAuthorize(): CancelablePromise<string> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/connector/oauth/authorize',
        });
    }
    /**
     * Consent
     * Finish the durable consent using explicit allow/deny, consent_id and its one-time CSRF
     * token bound to the same live Manager session. Accepts application/x-www-form-urlencoded
     * up to 8192 bytes; duplicate parameters are rejected. Success redirects with 303 to the
     * registered callback; OAuth errors use error/error_description. Do not blindly replay a
     * consumed consent.
     *
     * See [connector access and
     * scopes](https://github.com/mvnby/air-api/blob/main/docs/chatgpt-connector.md#адрес-и-доступ).
     * MCP transport and tools/list are outside this HTTP schema.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static connectorOauthConsent(): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/connector/oauth/authorize',
        });
    }
    /**
     * Token
     * Exchange an authorization code with PKCE or rotate a refresh token for the registered
     * public client and exact MCP resource. Accepts application/x-www-form-urlencoded up to
     * 8192 bytes; duplicate fields, Authorization/client_secret and unsupported grants are
     * rejected. No Manager JWT is used here. Refresh reuse revokes the grant; after losing a
     * refresh response do not treat the old token as safely replayable. OAuth errors use
     * error/error_description; responses are no-store.
     *
     * See [connector access and
     * scopes](https://github.com/mvnby/air-api/blob/main/docs/chatgpt-connector.md#адрес-и-доступ).
     * MCP transport and tools/list are outside this HTTP schema.
     * @returns ConnectorTokenResponse Successful Response
     * @throws ApiError
     */
    public static connectorOauthToken(): CancelablePromise<ConnectorTokenResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/connector/oauth/token',
        });
    }
    /**
     * Revoke
     * Revoke a connector access/refresh token using its registered client_id. Accepts
     * application/x-www-form-urlencoded up to 8192 bytes; duplicate fields are rejected.
     * Success has an empty 200 body and no-store headers. No Manager JWT is used for this
     * token endpoint; errors use OAuth error/error_description.
     *
     * See [connector access and
     * scopes](https://github.com/mvnby/air-api/blob/main/docs/chatgpt-connector.md#адрес-и-доступ).
     * MCP transport and tools/list are outside this HTTP schema.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static connectorOauthRevoke(): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/connector/oauth/revoke',
        });
    }
    /**
     * Grants
     * List OAuth grants belonging to the current authenticated Manager actor and return a
     * session-bound CSRF token for profile revocation. Response is no-store; does not list
     * other users’ grants.
     *
     * See [connector access and
     * scopes](https://github.com/mvnby/air-api/blob/main/docs/chatgpt-connector.md#адрес-и-доступ).
     * MCP transport and tools/list are outside this HTTP schema.
     * @returns ConnectorGrantListResponse Successful Response
     * @throws ApiError
     */
    public static managerConnectorGrants(): CancelablePromise<ConnectorGrantListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/connector/grants',
        });
    }
    /**
     * Manager Revoke
     * Revoke the current Manager actor’s grant using X-CSRF-Token bound to that Manager
     * credential. Requires live Manager access and grant ownership; success is 204 with no
     * body/no-store headers. OAuth policy errors use error/error_description. Removing a
     * client plugin alone does not invoke this revocation.
     *
     * See [connector access and
     * scopes](https://github.com/mvnby/air-api/blob/main/docs/chatgpt-connector.md#адрес-и-доступ).
     * MCP transport and tools/list are outside this HTTP schema.
     * @param grantId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static managerConnectorRevoke(
        grantId: number,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/connector/grants/{grant_id}/revoke',
            path: {
                'grant_id': grantId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
