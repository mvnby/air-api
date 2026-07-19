/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BotStaffNotificationNackRequest = {
    worker_id: string;
    lease_token: string;
    permanent?: boolean;
    error_code: string;
    retry_after_seconds?: (number | null);
};

