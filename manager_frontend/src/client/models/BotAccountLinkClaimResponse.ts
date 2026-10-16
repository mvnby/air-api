/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BotAccountLinkClaimResponse = {
    challenge_id: string;
    purpose: 'link' | 'login';
    status: 'claimed' | 'approval_pending' | 'approved';
    expires_at: string;
    browser_code?: (string | null);
};

