/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManagerStaffInvitationItem = {
    id: number;
    role: 'owner' | 'admin' | 'manager' | 'catalog_editor' | 'installer';
    created_at: string;
    expires_at: string;
    status: 'pending' | 'accepted' | 'revoked' | 'expired';
};

