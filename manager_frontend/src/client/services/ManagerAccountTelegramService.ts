/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TelegramChallengeResponse } from '../models/TelegramChallengeResponse';
import type { TelegramChallengeStartResponse } from '../models/TelegramChallengeStartResponse';
import type { TelegramDisconnectPayload } from '../models/TelegramDisconnectPayload';
import type { TelegramLinkConfirmPayload } from '../models/TelegramLinkConfirmPayload';
import type { TelegramLinkedResponse } from '../models/TelegramLinkedResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerAccountTelegramService {
    /**
     * Start Link
     * Create a five-minute proof for this account and browser. Requires X-Kitlane-Telegram:1 and approved Origin. Returns a private-bot deep link, never a Telegram numeric-ID input. A new challenge replaces pending challenges; no account is linked yet.
     * @returns TelegramChallengeStartResponse Successful Response
     * @throws ApiError
     */
    public static startManagerTelegramLink(): CancelablePromise<TelegramChallengeStartResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/account/telegram/link-challenges',
        });
    }
    /**
     * Link Status
     * Read the candidate Telegram profile only in the originating browser and unchanged account session. Unknown/browser-mismatched challenges return404; expired proofs report expired. This GET never links or consumes a proof.
     * @param challengeId
     * @returns TelegramChallengeResponse Successful Response
     * @throws ApiError
     */
    public static getManagerTelegramLink(
        challengeId: string,
    ): CancelablePromise<TelegramChallengeResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/account/telegram/link-challenges/{challenge_id}',
            path: {
                'challenge_id': challengeId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Confirm Link
     * Confirm exactly the bot-proven profile shown by the browser. Atomically links the current account, records proof/audit and rotates auth_version, refreshing this browser cookie. Requires the original challenge cookie, X-Kitlane-Telegram:1 and approved Origin. Expired/replayed/conflicting proofs return409; an existing other account is never merged or stolen.
     * @param challengeId
     * @param requestBody
     * @returns TelegramLinkedResponse Successful Response
     * @throws ApiError
     */
    public static confirmManagerTelegramLink(
        challengeId: string,
        requestBody: TelegramLinkConfirmPayload,
    ): CancelablePromise<TelegramLinkedResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/account/telegram/link-challenges/{challenge_id}/confirm',
            path: {
                'challenge_id': challengeId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Disconnect
     * Remove this account's Telegram binding only after verifying its alternate username/password login. Clears the contractor mirror, rotates auth_version and refreshes the current browser cookie. Requires X-Kitlane-Telegram:1 and approved Origin; no alternate factor returns409. Does not delete the account or revoke company membership.
     * @param requestBody
     * @returns void
     * @throws ApiError
     */
    public static disconnectManagerTelegram(
        requestBody: TelegramDisconnectPayload,
    ): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/account/telegram',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
