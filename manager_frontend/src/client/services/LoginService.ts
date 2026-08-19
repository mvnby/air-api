/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_login_access_token } from '../models/Body_login_access_token';
import type { TelegramLoginPayload } from '../models/TelegramLoginPayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class LoginService {
    /**
     * Login Access Token
     * OAuth2 compatible token login, get an access token for future requests.
     * Sets 'access_token' cookie as well.
     * @param formData
     * @returns any Successful Response
     * @throws ApiError
     */
    public static loginAccessToken(
        formData: Body_login_access_token,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/login/access-token',
            formData: formData,
            mediaType: 'application/x-www-form-urlencoded',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Logout
     * End the browser cookie session without requiring a valid token.
     *
     * Access tokens are intentionally stateless JWTs, so this endpoint cannot
     * revoke a token that was deliberately copied to an Authorization header.
     * The manager UI uses the HttpOnly cookie only; deleting the cookie is the
     * server-side session boundary for a normal browser logout.
     * @returns void
     * @throws ApiError
     */
    public static logoutAccessToken(): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/login/logout',
        });
    }
    /**
     * Login Telegram
     * @param requestBody
     * @returns any Successful Response
     * @throws ApiError
     */
    public static loginTelegram(
        requestBody: TelegramLoginPayload,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/login/telegram',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
