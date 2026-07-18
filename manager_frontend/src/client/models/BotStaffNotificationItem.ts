/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotStaffNotificationPayload } from './BotStaffNotificationPayload';
export type BotStaffNotificationItem = {
    delivery_id: string;
    event_id: string;
    telegram_id: number;
    payload: BotStaffNotificationPayload;
    attempt: number;
    max_attempts: number;
    lease_token: string;
    lease_expires_at: string;
};

