/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerStaffInvitationCreate } from '../models/ManagerStaffInvitationCreate';
import type { ManagerStaffInvitationCreated } from '../models/ManagerStaffInvitationCreated';
import type { ManagerStaffInvitationList } from '../models/ManagerStaffInvitationList';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerTeamService {
    /**
     * Create Invitation
     * Create a seven-day manual invitation. Requires X-Kitlane-Team:1 and approved Origin.
     *
     * Live owner/admin hierarchy determines assignable roles; platform support uses verified
     * owner authority. Returns its bearer URL only once. No email is sent, no user is created
     * and no catalog permission is granted. Legacy recovery identities without staff return403.
     * @param requestBody
     * @returns ManagerStaffInvitationCreated Successful Response
     * @throws ApiError
     */
    public static managerCreateStaffInvitation(
        requestBody: ManagerStaffInvitationCreate,
    ): CancelablePromise<ManagerStaffInvitationCreated> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/staff/invitations',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Invitations
     * List invitation status in the selected company; never returns tokens or password data.
     * @param page
     * @param limit
     * @returns ManagerStaffInvitationList Successful Response
     * @throws ApiError
     */
    public static managerListStaffInvitations(
        page: number = 1,
        limit: number = 50,
    ): CancelablePromise<ManagerStaffInvitationList> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/staff/invitations',
            query: {
                'page': page,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Revoke Invitation
     * Revoke a pending invitation with live hierarchy checks and an atomic audit receipt.
     *
     * Requires X-Kitlane-Team:1 and approved Origin. Accepted links cannot grant access again;
     * revoking an already finished invitation does not change its existing membership.
     * @param invitationId
     * @returns void
     * @throws ApiError
     */
    public static managerRevokeStaffInvitation(
        invitationId: number,
    ): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/staff/invitations/{invitation_id}',
            path: {
                'invitation_id': invitationId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
