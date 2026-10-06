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
