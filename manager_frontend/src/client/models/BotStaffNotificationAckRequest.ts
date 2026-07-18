/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BotStaffNotificationAckRequest = {
    worker_id: string;
    lease_token: string;
    telegram_message_id: number;
    provider_latency_ms?: (number | null);
};

