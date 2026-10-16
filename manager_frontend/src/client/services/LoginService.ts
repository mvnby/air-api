/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_login_access_token } from '../models/Body_login_access_token';
import type { TelegramChallengeResponse } from '../models/TelegramChallengeResponse';
import type { TelegramChallengeStartResponse } from '../models/TelegramChallengeStartResponse';
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
    /**
     * Start Login
     * Create a rate-limited five-minute anonymous browser login challenge. Requires X-Kitlane-Telegram:1 and approved Origin. Returns a deep link and eight-digit browser matching code; the private bot must explicitly approve. This operation creates no staff account and issues no login cookie.
     * @returns TelegramChallengeStartResponse Successful Response
     * @throws ApiError
     */
    public static startTelegramLogin(): CancelablePromise<TelegramChallengeStartResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/login/telegram/challenges',
        });
    }
    /**
     * Login Status
     * Read pending/approved/denied/expired status only with the originating browser secret. Does not log in or consume the approval; mismatched browser returns404.
     * @param challengeId
     * @returns TelegramChallengeResponse Successful Response
     * @throws ApiError
     */
    public static getTelegramLogin(
        challengeId: string,
    ): CancelablePromise<TelegramChallengeResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/login/telegram/challenges/{challenge_id}',
            path: {
                'challenge_id': challengeId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Complete Login
     * Consume an explicit bot approval in its original browser. Requires X-Kitlane-Telegram:1 and approved Origin; revalidates active identity, unchanged auth_version, live membership and legacy-owner fence. Issues the normal HttpOnly login cookie and JWT response. Replay/expiry or changed access rejects the login; never creates an account.
     * @param challengeId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static completeTelegramLogin(
        challengeId: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/login/telegram/challenges/{challenge_id}/complete',
            path: {
                'challenge_id': challengeId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
