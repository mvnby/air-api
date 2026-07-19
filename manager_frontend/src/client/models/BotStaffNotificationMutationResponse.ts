/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BotStaffNotificationMutationResponse = {
    delivery_id: string;
    status: 'running' | 'sent' | 'retry' | 'dead';
    lease_expires_at?: (string | null);
    next_attempt_at?: (string | null);
};

