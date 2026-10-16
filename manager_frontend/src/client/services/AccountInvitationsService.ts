/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { StaffInvitationAcceptCredentials } from '../models/StaffInvitationAcceptCredentials';
import type { StaffInvitationAccepted } from '../models/StaffInvitationAccepted';
import type { StaffInvitationAcceptExisting } from '../models/StaffInvitationAcceptExisting';
import type { StaffInvitationAcceptNew } from '../models/StaffInvitationAcceptNew';
import type { StaffInvitationPreview } from '../models/StaffInvitationPreview';
import type { StaffInvitationToken } from '../models/StaffInvitationToken';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class AccountInvitationsService {
    /**
     * Preview Invitation
     * Preview company name, role and expiry from a bearer token carried in JSON, not a URL query.
     *
     * No account lookup or membership mutation occurs. Invalid, expired, used, revoked or
     * unavailable-company invitations return404. Preview does not consume the token.
     * @param requestBody
     * @returns StaffInvitationPreview Successful Response
     * @throws ApiError
     */
    public static previewStaffInvitation(
        requestBody: StaffInvitationToken,
    ): CancelablePromise<StaffInvitationPreview> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/account/invitations/preview',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Accept Invitation
     * Accept once using an existing session, explicit account credentials, or a new strong password.
     *
     * Requires X-Kitlane-Team:1 and approved Origin. Password proof is rate limited. Live inviter
     * authority is checked under locks; no email matching, password reset, existing-membership
     * upgrade, catalog grant or blocked/merged account reactivation occurs. A returning inactive
     * person can prove their existing password and join a new company while all old memberships
     * stay disabled; auth_version increments. New/credential modes set a normal HttpOnly cookie.
     * @param requestBody
     * @returns StaffInvitationAccepted Successful Response
     * @throws ApiError
     */
    public static acceptStaffInvitation(
        requestBody: (StaffInvitationAcceptExisting | StaffInvitationAcceptNew | StaffInvitationAcceptCredentials),
    ): CancelablePromise<StaffInvitationAccepted> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/account/invitations/accept',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
